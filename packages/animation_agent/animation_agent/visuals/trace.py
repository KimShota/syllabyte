"""
Trace-first worked examples: code runs the algorithm, the writer narrates the steps. No Manim import.

The template steps were already computed (a sort step or a bisection check is what the algorithm really does), but
the writer chose which step calls to make, and its plan of them was often incoherent: across five runs of the
bisection video (runs/course-test-1 .. runs/lines-fix-1) it restarted the search, changed the target half way, or
mixed a hand-made swap into a computed sort, and every fix after that (numbers, fronts, matched lines) could only
patch the lines around a muddled picture. So for a KU that steps through one of these algorithms, a short call
picks the example (script_generation_agent.picture_plan.plan_example), code computes every step here, the writer
is shown them as numbered sentences, and it shows them with `<name>.next_step()`, which code expands into the
step's call. The writer can choose which beat shows which step, but not change or reorder them.

The data structures are traced the same way: a BST's or a heap's operations (one comparison or swap per step, the
templates' *_step actions), a graph search or algorithm (one node, level or edge per step), and a linked list's
search or reversal (one node per step). Code runs the template's own checks until the algorithm ends, so the steps
are what the checker and the renderer compute.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from animation_agent.visuals.specs import (
    _ms_ready,
    bisect_next,
    ms_merge,
    ms_merge_step,
    ms_new,
    ms_split,
    sort_events,
)

Algorithm = Literal["linear_search", "bisection", "bubble_sort", "selection_sort", "insertion_sort", "merge_sort",
                    "merge", "bst", "heap", "dfs", "bfs", "dijkstra", "prim", "kruskal", "topological_sort",
                    "linked_list", "none"]

TEMPLATE_OF = {"linear_search": "ArrayBars", "bisection": "ArrayBars", "bubble_sort": "ArrayBars",
               "selection_sort": "ArrayBars", "insertion_sort": "ArrayBars", "merge_sort": "MergeSort",
               "merge": "MergeSort", "bst": "BinaryTree", "heap": "BinaryTree", "dfs": "Graph", "bfs": "Graph",
               "dijkstra": "Graph", "prim": "Graph", "kruskal": "Graph", "topological_sort": "Graph",
               "linked_list": "LinkedList"}

# The calls that run an algorithm (or change the values it runs on): on the traced object, only next_step does.
STEP_ACTIONS = {
    "ArrayBars": {"scan", "bisect_check", "bisect_discard", "bisect_step", "bubble_step", "bubble_pass",
                  "selection_step", "insertion_step", "swap", "set_value"},
    "MergeSort": {"split", "merge_step", "merge", "merge_level"},
    "BinaryTree": {"insert", "search", "delete", "push", "pop", "heapify", "traverse_step", "insert_step",
                   "search_step", "push_step", "pop_step", "heapify_step"},
    "Graph": {"dfs_step", "bfs_level", "dijkstra_step", "prim_step", "kruskal_step", "topo_step"},
    "LinkedList": {"insert", "delete", "find_step", "reverse_step"},
}
MAX_STEPS = 20
MAX_PER_BEAT = 3


class Op(BaseModel):
    """One operation on the example's BST, heap or linked list."""

    op: Literal["insert", "search", "delete", "push", "pop", "heapify", "traverse", "find", "reverse"] = Field(
        description="BST: insert, search, delete, traverse; heap: push, pop, heapify (heapify only first, on an "
                    "array that isn't a heap yet), traverse; linked list: insert, delete, find, reverse")
    value: int | None = Field(None, description="the value inserted, searched for, deleted (BST) or pushed")
    index: int | None = Field(None, description="linked list insert and delete: the position (0 = the head)")
    order: Literal["inorder", "preorder", "postorder", "level"] | None = Field(None, description="traverse only")


TreeOp = Op


class Example(BaseModel):
    """The worked example a video steps through."""

    algorithm: Algorithm = Field(description="the algorithm the video runs step by step on the example, or none")
    values: list[int] = Field(default_factory=list,
                              description="lists: 4-8 whole numbers from 0 to 99 (sorted for bisection); bst: "
                                          "the tree's values in the order inserted (0-9 of them, the first is the "
                                          "root); heap: its array (0-9); linked_list: the list from the head, "
                                          "3-5 one-digit numbers; for merge, leave empty and give runs")
    runs: list[list[int]] = Field(default_factory=list,
                                  description="merge only: the two sorted lists merged, 2-8 numbers in all")
    target: int | None = Field(None, description="linear_search, bisection: the value searched for")
    heap: Literal["min", "max"] = Field("min", description="heap only: a min-heap or a max-heap")
    ops: list[Op] = Field(default_factory=list,
                          description="bst, heap, linked_list: the operations shown, in order (1-3)")
    nodes: list[str] = Field(default_factory=list,
                             description="graphs: 4-7 node names of 1-2 characters, e.g. [\"s\", \"a\", \"b\"]")
    edges: list[list[str]] = Field(default_factory=list,
                                   description="graphs: pairs of node names (at most 10); for dijkstra, prim and "
                                               "kruskal each has its weight as a third item, e.g. [\"s\", \"a\", "
                                               "\"4\"]")
    directed: bool = Field(False, description="graphs: edges are arrows (topological_sort needs it)")
    start: str | None = Field(None, description="dfs, bfs, dijkstra, prim: the node it starts from")
    reason: str = Field("", description="one short sentence: where the example comes from")


@dataclass
class Trace:
    example: Example
    template: str
    create: str  # the creation call's arguments, e.g. "values=[1, 3, 4, 7]"
    steps: list[str]  # each step's call on the object, as ".action(args)"
    said: list[str]  # what each step shows, computed from the calls
    log: list[str] = field(default_factory=list)
    match: dict = field(default_factory=dict)  # the creation arguments that make an object the example
    task: str = ""  # what the steps do, in words ("bisection for 13", "insert 7, then search for 5")


def _bisection(values: list[int], target: int) -> list[str]:
    out, lo, hi = [], 0, len(values) - 1
    while lo <= hi:
        out += [f".bisect_check(target={target})", ".bisect_discard()"]
        _, lo, hi, found = bisect_next(values, lo, hi, target)
        if found:
            break
    return out


def _linear(values: list[int], target: int) -> list[str]:
    out = []
    for i, v in enumerate(values):
        out.append(f".scan(index={i}, target={target})")
        if v == target:
            break
    return out


def _sort(values: list[int], kind: str) -> list[str]:
    """Each step of the sort; bubble sort's first pass one comparison at a time, then a pass per step."""
    vals, st, out = list(values), None, []
    while st is None or not st["done"]:
        whole = kind == "bubble" and st is not None and st["pass"] > 1
        st, events = sort_events(vals, st, kind, whole_pass=whole)
        if not events:
            break
        out.append(f".{kind}_pass()" if whole else f".{kind}_step()")
    return out


def _merge_sort(values: list[int] | None, runs: list[list[int]] | None) -> list[str]:
    """Split level by level, merge every level but the last whole, then the last merge front by front (the merge
    a lesson on merging is about)."""
    st, out = ms_new(values, runs), []
    while st["splittable"] and ms_split(st) is None:
        out.append(".split()")
    while not st["tree"]["sorted"] and len(out) < MAX_STEPS:
        ready = _ms_ready(st)
        if st["merge"] is not None or (ready and ready[0] is st["tree"]):
            ev = ms_merge_step(st)
            if isinstance(ev, str):
                break
            out.append(".merge_step()")
        else:
            if isinstance(ms_merge(st, whole_level=True), str):
                break
            out.append(".merge_level()")
    return out


def _arg(v) -> str:
    return repr(v) if isinstance(v, bool) else json.dumps(v)


def _call(action: str, args: dict) -> str:
    return f".{action}({', '.join(f'{k}={_arg(v)}' for k, v in args.items())})"


class _Run:
    """The example's object as the checker holds it: step calls applied with the template's own checks."""

    def __init__(self, template: str, kwargs: dict):
        from animation_agent.visuals.specs import REGISTRY

        self.spec = REGISTRY[template]
        self.params = self.spec.params.model_validate(kwargs)
        self.st = self.spec.init_state(self.params) | {"_noun": self.spec.noun}

    def do(self, action: str, **args) -> bool:
        a = self.spec.all_actions()[action]
        return not (a.check and a.check(self.st, a.args.model_validate(args)))


def _loop(run: _Run, action: str, args: dict, finished, dropped=lambda st: False) -> list[str]:
    """`action` called until `finished(state)`, or until a call is refused or shows nothing (`dropped`), which
    isn't kept. At most MAX_STEPS + 1 calls (more is rejected by the caller)."""
    out = []
    while len(out) <= MAX_STEPS:
        if not run.do(action, **args) or dropped(run.st):
            break
        out.append(_call(action, args))
        if finished(run.st):
            break
    return out


def _tree_kwargs(ex: Example) -> dict:
    """The tree as created: a heap's array made a heap first, unless the video heapifies it."""
    from animation_agent.visuals.specs import bt_new, heap_heapify

    if ex.algorithm == "bst":
        return {"kind": "bst", "values": list(ex.values)}
    kind = f"{ex.heap}_heap"
    values = list(ex.values)
    if not (ex.ops and ex.ops[0].op == "heapify"):
        st = bt_new(kind, values)
        heap_heapify(st)
        values = st["heap"]
    return {"kind": kind, "values": values}


_TREE_STEP = {"insert": "insert_step", "search": "search_step", "push": "push_step", "pop": "pop_step",
              "heapify": "heapify_step"}


def _tree_steps(run: _Run, ops: list[TreeOp]) -> tuple[list[str], list[str]]:
    """Each operation's steps, one comparison or swap each; operations past MAX_STEPS are left out. Returns the
    steps and the operations kept, in words."""
    steps, words = [], []
    for op in ops:
        if op.op == "traverse":
            if op.order is None:
                break
            n = len(run.st["heap"]) if run.st["kind"] != "bst" else len(run.st["nodes"])
            more = []
            for _ in range(n):
                if not run.do("traverse_step", order=op.order):
                    break
                more.append(_call("traverse_step", {"order": op.order}))
            what = f"{op.order} traversal"
        elif op.op == "delete":
            if op.value is None or not run.do("delete", value=op.value):
                break
            more, what = [_call("delete", {"value": op.value})], f"delete {op.value}"
        else:
            args = {} if op.op in ("pop", "heapify") else {"value": op.value}
            if op.op not in ("pop", "heapify") and op.value is None:
                break
            more = _loop(run, _TREE_STEP[op.op], args, lambda st: st["op"] is None)
            if not more or run.st["op"] is not None:
                break
            what = op.op + (f" {op.value}" if op.value is not None else "")
            what = "search for " + what.split()[1] if op.op == "search" else what
        if not more or len(steps) + len(more) > MAX_STEPS:
            break
        steps += more
        words.append(what)
    return steps, words


_GRAPH_STEP = {"dfs": "dfs_step", "bfs": "bfs_level", "dijkstra": "dijkstra_step", "prim": "prim_step",
               "kruskal": "kruskal_step", "topological_sort": "topo_step"}


def _graph_steps(run: _Run, ex: Example) -> list[str]:
    algo = ex.algorithm
    start = ex.start if ex.start is not None else (ex.nodes[0] if ex.nodes else None)
    args = {"start": start} if algo in ("dfs", "bfs", "dijkstra", "prim") else {}
    if algo == "dfs":
        return _loop(run, "dfs_step", args, lambda st: st["search"]["done"])
    if algo == "bfs":
        return _loop(run, "bfs_level", args, lambda st: False, lambda st: st["last"]["level"] is None)
    empty = {"dijkstra": lambda ev: ev["settled"] is None, "prim": lambda ev: ev.get("added") is None,
             "kruskal": lambda ev: ev["edge"] is None,
             "topological_sort": lambda ev: ev["node"] is None and not ev["cycle"]}[algo]
    return _loop(run, _GRAPH_STEP[algo], args, lambda st: st["algo"]["done"], lambda st: empty(st["last"]))


def _list_steps(run: _Run, ops: list[Op]) -> tuple[list[str], list[str]]:
    """A linked list's operations: insert and delete one step each, find and reverse one node per step."""
    steps, words = [], []
    for op in ops:
        if op.op == "insert" and op.index is not None and op.value is not None:
            args = {"index": op.index, "value": op.value}
            more = [_call("insert", args)] if run.do("insert", **args) else []
            what = f"insert {op.value} at position {op.index}"
        elif op.op == "delete" and op.index is not None:
            more = [_call("delete", {"index": op.index})] if run.do("delete", index=op.index) else []
            what = f"delete position {op.index}"
        elif op.op in ("find", "search") and op.value is not None:
            more = _loop(run, "find_step", {"value": op.value}, lambda st: st["find"]["done"])
            what = f"search for {op.value}"
        elif op.op == "reverse":
            more = _loop(run, "reverse_step", {}, lambda st: st["rev"]["done"])
            what = "reverse it in place"
        else:
            break
        if not more or len(steps) + len(more) > MAX_STEPS:
            break
        steps += more
        words.append(what)
    return steps, words


def _structure_trace(ex: Example) -> tuple[str, dict, list[str], str] | None:
    """A data structure's example: (template, creation arguments, steps, what they do), or None if it doesn't
    fit."""
    from pydantic import ValidationError

    template = TEMPLATE_OF[ex.algorithm]
    if template == "BinaryTree":
        kwargs = _tree_kwargs(ex)
    elif template == "Graph":
        kwargs = {"nodes": list(ex.nodes), "edges": [list(e) for e in ex.edges]} | (
            {"directed": True} if ex.directed else {})
    else:
        kwargs = {"values": list(ex.values)}
    try:
        run = _Run(template, kwargs)
    except (ValidationError, KeyError, TypeError, ValueError):
        return None
    if template == "BinaryTree":
        steps, words = _tree_steps(run, ex.ops)
        task = ", then ".join(words)
    elif template == "Graph":
        steps = _graph_steps(run, ex)
        start = ex.start if ex.start is not None else ex.nodes[0]
        name = {"dfs": "DFS", "bfs": "BFS", "dijkstra": "Dijkstra", "prim": "Prim's minimum spanning tree",
                "kruskal": "Kruskal's minimum spanning tree", "topological_sort": "a topological order"}[ex.algorithm]
        task = name + (f" from {start}" if ex.algorithm in ("dfs", "bfs", "dijkstra", "prim") else "")
    else:
        steps, words = _list_steps(run, ex.ops)
        task = ", then ".join(words)
    return template, kwargs, steps, task


def build_trace(example: Example) -> Trace | None:
    """The example's steps and what each shows, or None when there is no algorithm or the example doesn't fit its
    template (code then leaves the steps to the writer, as before)."""
    from animation_agent.visuals.calls import check_segment, describe_segment

    ex = example
    if ex.algorithm == "none":
        return None
    template = TEMPLATE_OF[ex.algorithm]
    if template not in ("ArrayBars", "MergeSort"):
        built = _structure_trace(ex)
        if built is None:
            return None
        template, kwargs, steps, task = built
        create = ", ".join(f"{k}={_arg(v)}" for k, v in kwargs.items())
        if not steps or len(steps) > MAX_STEPS:
            return None
        draws = [[f"x = {template}({create})"], *[[f"x{s}"] for s in steps]]
        if check_segment(draws):
            return None
        match = {k: v for k, v in kwargs.items()}
        return Trace(ex, template, create, steps, describe_segment(draws)[1:], match=match, task=task)
    searches = ex.algorithm in ("linear_search", "bisection")
    if (searches and ex.target is None) or (ex.algorithm == "merge") != bool(ex.runs):
        return None
    if ex.algorithm == "merge":
        create = f"runs={[list(r) for r in ex.runs]}"
    else:
        create = f"values={list(ex.values)}" + (', style="bars"' if ex.algorithm.endswith("_sort")
                                                 and template == "ArrayBars" else "")
    try:
        steps = {"bisection": lambda: _bisection(ex.values, ex.target),
                 "linear_search": lambda: _linear(ex.values, ex.target),
                 "bubble_sort": lambda: _sort(ex.values, "bubble"),
                 "selection_sort": lambda: _sort(ex.values, "selection"),
                 "insertion_sort": lambda: _sort(ex.values, "insertion"),
                 "merge_sort": lambda: _merge_sort(ex.values, None),
                 "merge": lambda: _merge_sort(None, ex.runs)}[ex.algorithm]()
    except (IndexError, KeyError, TypeError, ValueError):
        return None
    if not steps or len(steps) > MAX_STEPS:
        return None
    draws = [[f"x = {template}({create})"], *[[f"x{s}"] for s in steps]]
    if check_segment(draws):
        return None
    said = describe_segment(draws)[1:]
    match = {"runs": ex.runs} if ex.algorithm == "merge" else {"values": ex.values}
    task = ex.algorithm.replace("_", " ") + (f" for {ex.target}" if ex.target is not None else "")
    return Trace(ex, template, create, steps, said, match=match, task=task)


def _parts(text: str):
    """("create", name, template, kwargs) or ("act", name, action, kwargs), or None if it isn't a plain call."""
    from animation_agent.visuals.calls import _as_raw_strings

    try:
        stmt = ast.parse(_as_raw_strings(text.strip())).body[0]
        call = stmt.value
        kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
    except Exception:  # noqa: BLE001 - anything unparsable is the checker's to report
        return None
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name) \
            and isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
        return "create", stmt.targets[0].id, call.func.id, kwargs
    if isinstance(stmt, ast.Expr) and isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) \
            and isinstance(call.func.value, ast.Name):
        return "act", call.func.value.id, call.func.attr, kwargs
    return None


_DEFAULTS = {"directed": False, "kind": "bst"}


def _is_example(trace: Trace, template: str, kwargs: dict) -> bool:
    return template == trace.template and all(kwargs.get(k, _DEFAULTS.get(k)) == v for k, v in trace.match.items())


def _same_action(what: str, step: str) -> bool:
    nxt = step[1:].split("(", 1)[0]
    return what == nxt or (what.startswith("bisect") and nxt.startswith("bisect"))


def apply_trace(segments: list[list[list[str]] | None], trace: Trace,
                ) -> tuple[list[list[list[str]] | None], list[str], list[tuple[int, int, str]]]:
    """The calls with each `<example>.next_step(count=k)` replaced by the example's next k steps. What strays
    from the trace is also brought onto it, and reported (segment, 1-based beat, message) so a first draft can be
    written again: a step call of the writer's own on the example takes the next step instead; a next_step past
    the last step, or on an object that isn't the example, is dropped. Returns (segments, log, problems)."""
    out: list[list[list[str]] | None] = []
    log: list[str] = []
    problems: list[tuple[int, int, str]] = []
    name: str | None = None  # the example's object, once created
    k = 0
    created = False
    for s, draws in enumerate(segments):
        if draws is None:
            out.append(None)
            continue
        seg = []
        for b, calls in enumerate(draws, 1):
            beat = []
            for text in calls:
                parts = _parts(text)
                if parts is None:
                    beat.append(text)
                    continue
                kind, obj, what, kwargs = parts
                if kind == "create":
                    if _is_example(trace, what, kwargs):
                        if created and obj == name:
                            log.append(f"segment {s} beat {b}: the example is created again; its steps start over")
                        name, k, created = obj, 0, True
                    elif obj == name:
                        name = None  # replaced by something else: the example is gone
                    beat.append(text)
                    continue
                own = obj == name and what in STEP_ACTIONS.get(trace.template, ())
                if what != "next_step" and not own:
                    beat.append(text)
                    continue
                if obj != name:
                    problems.append((s, b, f"beat {b}, `{text}`: next_step runs only the worked example "
                                           "(create it with exactly its values first)"))
                    continue
                want = 2 if what == "bisect_step" else 1
                if what == "next_step":
                    count = kwargs.get("count", 1)
                    want = max(1, min(MAX_PER_BEAT, count if isinstance(count, int) else 1))
                take = trace.steps[k:k + want]
                if own and take and not _same_action(what, take[0]):
                    # Another operation of its own (an insert where the trace searches): taking the next step in
                    # its place would draw something its line doesn't say, so it is dropped and reported.
                    problems.append((s, b, f"beat {b}, `{text}`: the worked example's steps are computed, and the "
                                           f"next is step {k + 1}: {trace.said[k]} Show it with {name}.next_step(); "
                                           "for another operation, create a second object"))
                    continue
                if own:
                    problems.append((s, b, f"beat {b}, `{text}`: the worked example's steps are computed: show "
                                           f"them with {name}.next_step(), in order (this was step {k + 1}: "
                                           f"{trace.said[k] if k < len(trace.said) else 'past the last step'})"))
                if not take:
                    problems.append((s, b, f"beat {b}, `{text}`: the worked example has only {len(trace.steps)} "
                                           "steps, all shown already"))
                    continue
                beat += [f"{name}{step}" for step in take]
                k += len(take)
            seg.append(beat)
        out.append(seg)
    if not created:
        problems.append((0, 1, f"the worked example is never created: create it once as "
                               f"`name = {trace.template}({trace.create}, ...)` and show its steps with next_step"))
    return out, log, problems


# What the fix call may not do to the example: run, restart or rewind it (restore un-greys a search's cells while
# the search goes on), or create it again. In runs/trace-fix-1 the writer's bisection followed the trace, then the
# fix call, asked to make a text-only objective "take a step", ran two of its own and restarted the search twice.
_KEPT = {"ArrayBars": {"restore", "grey_out", "found"}, "MergeSort": set(), "Graph": {"reset"}}


def example_name(segments: list[list[list[str]] | None], trace: Trace) -> str | None:
    """The name the example is created under, if it is."""
    for draws in segments:
        for calls in draws or []:
            for text in calls:
                parts = _parts(text)
                if parts and parts[0] == "create" and _is_example(trace, parts[2], parts[3]):
                    return parts[1]
    return None


def keep_steps(before: list[list[list[str]] | None], after: list[list[list[str]] | None], trace: Trace,
               ) -> tuple[list[list[list[str]] | None], list[str]]:
    """`after` (the fix call's calls) with the example's steps as they were in `before`: every step, restart or
    creation of the example the fix call added is removed, and every one it removed or moved is put back where it
    was. The rest of the fix (highlights, pointers, notes, other objects) stays."""
    name = example_name(before, trace)
    if name is None:
        return after, []
    actions = STEP_ACTIONS.get(trace.template, set()) | _KEPT.get(trace.template, set())

    def kept(text: str) -> bool:
        parts = _parts(text)
        return bool(parts) and parts[1] == name and (parts[0] == "create" or parts[2] in actions)

    out, log = [], []
    for s, (old, new) in enumerate(zip(before, after)):
        if old is None or new is None or len(old) != len(new):
            out.append(new)
            continue
        seg = []
        for b, (o, n) in enumerate(zip(old, new), 1):
            beat = [c for c in n if not kept(c)]
            for i, text in enumerate(o):
                if kept(text):
                    beat.insert(min(i, len(beat)), text)
            if [c for c in beat if kept(c)] != [c for c in n if kept(c)]:
                log.append(f"segment {s} beat {b}: kept the worked example's steps as they were (the fix call "
                           f"changed them: {[c for c in n if kept(c)]})")
            seg.append(beat)
        out.append(seg)
    return out, log


FIX_NOTE = ("\n\nThe object `{name}` is the worked example: code computed its steps, and the lines narrate them in "
            "order. Don't add, remove or move its step calls ({actions}), and don't create it again: show a point "
            "with highlights, pointers, ghosts or notes on it instead.")


def trace_brief(trace: Trace) -> str:
    """The example as the writer is shown it: how to create it, and its steps in order."""
    ex = trace.example
    numbered = "\n".join(f"  {i}. {said}" for i, said in enumerate(trace.said, 1))
    pair = (": a check and its discard may share one (`name.next_step(count=2)`)"
            if ex.algorithm == "bisection" else ": a line can't follow two")
    target = f" for {ex.target}" if ex.target is not None else ""
    if trace.template in ("ArrayBars", "MergeSort"):
        what = f"{ex.algorithm.replace('_', ' ')} on {trace.create.split(', style')[0].split('=', 1)[1]}{target}"
    else:
        from animation_agent.visuals.specs import REGISTRY

        spec = REGISTRY[trace.template]
        what = f"{trace.task}, on {spec.describe(spec.params.model_validate(trace.match))}"
    return f"""

The worked example (code picked it and computed every step, so the steps below are exactly what the picture shows):
  {what}.
Create it once as `name = {trace.template}({trace.create}, ...)`: choose the name and a title, keep these values. \
Then show its steps only with `name.next_step()`: each call shows the next step below, in order. One step per \
line{pair}. Its steps:
{numbered}
You needn't show every step, but you can't skip or reorder them, and the example has no other step calls \
({", ".join(sorted(STEP_ACTIONS[trace.template]))} are not used on it) and isn't created again with other values. \
So plan the beats around the steps: a question or predict line comes just before the step that answers it, the \
line with a step says what that step shows (its numbers, as above), and a line about a later step comes after \
it. Highlights, pointers, ghosts and notes on the example are yours to add. To show a second case, create a \
second object with other values; its steps are then yours to call."""


__all__ = ["Example", "FIX_NOTE", "Op", "Trace", "apply_trace", "build_trace", "example_name", "keep_steps", "trace_brief",
           "TEMPLATE_OF"]
