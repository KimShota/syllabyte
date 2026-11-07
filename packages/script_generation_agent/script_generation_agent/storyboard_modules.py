"""
The storyboard prompt's part for each kind of picture: a worked Level 2 storyboard drawn with that kind's
templates, and a few rules for drawing it well.

Until now every Level 2 KU was shown the same worked example, linear search on a list of cells, whatever its
picture: in runs/general-3 the bar-chart, table, loop and polar videos never saw a storyboard using their own
template, and what the critic marked down was the writer's plan of the picture (a 3-box loop for a trajectory that
runs on, all 13 bars lit during a question). Prompting guidance and the research on it agree that examples teach
more than rules when they match the task (plan/one-shot-storyboard-plan.md, "Prompt modules per picture kind").
So the picture plan's family picks a module: its example replaces the generic one at Level 2 (the beat plans of
Levels 1 and 3 differ, so they keep their own example and get the module's rules), and its rules are added for
every level. A family with no module keeps the prompt as it was.

Each example is checked like the generic ones (tests/test_storyboard_modules.py): it matches the Level 2 plan,
passes the dialogue checks and the call checker with nothing for code to fix, so the prompt never shows a
storyboard the pipeline would reject. {explainer} and {peer} are the cast's names.
"""

from __future__ import annotations

from dataclasses import dataclass

from script_generation_agent.storyboard_example import SEGMENT_KEYS


@dataclass(frozen=True)
class Module:
    name: str
    families: frozenset[str]
    ku: str  # the example's Knowledge Unit ("" without one)
    example: dict | None  # None: the generic example stays, the rules are added
    rules: str


# --------------------------------------------------------------------------
# Boxes and arrows: trees, call trees, flowcharts, state machines
# --------------------------------------------------------------------------

_FIB = ('g = Graph(nodes=["r", "a", "b", "c", "d"], labels={"r": "fib(3)", "a": "fib(2)", "b": "fib(1)", '
        '"c": "fib(1)", "d": "fib(0)"}, edges=[["r", "a"], ["r", "b"], ["a", "c"], ["a", "d"]], directed=True, '
        'layout="tree", title="calls of fib(3)")')

BOXES = {
    "title": "Watching fib(3) call itself",
    "colour_key": [{"term": "call", "colour": "BLUE"}, {"term": "repeat", "colour": "ORANGE"}],
    "prepare": [
        ("b1_peer_question",
         [_FIB],
         "Lowkey, how can a function finish if it keeps calling itself?"),
        ("b2_explainer_build",
         ['g.highlight(nodes=["c", "d", "b"], colour="TEAL")'],
         "Each call asks smaller questions, until the bottom calls answer straight away."),
    ],
    "initiate": [
        ("b1_peer_question",
         [],
         "Okay, but why draw the calls as a tree?"),
        ("b2_explainer_objective",
         ["g.clear()", 'g.dfs_step(start="r")'],
         "You'll be able to trace the calls a recursion makes, starting from fib(3)."),
    ],
    "deliver_1": [
        ("b1_explainer_question",
         [],
         "{peer}, how many times does fib(3) work out fib(1)?"),
        ("b2_peer_answer_wrong_idea",
         ['g.ghost_edge(a="a", b="b", text="reuse fib(1)?")'],
         "Not gonna lie, just once: it reuses the answer it already has."),
        ("b3_explainer_feedback",
         ["g.clear()", 'g.highlight(nodes=["b", "c"], colour="ORANGE")'],
         "No, plain recursion remembers nothing, so both branches call fib(1) on their own."),
        ("b4_peer_build",
         ['g.dfs_step(start="r")', 'g.dfs_step(start="r")'],
         "So fib(2) goes first, and it calls fib(1) at the bottom left."),
        ("b5_explainer_build",
         ['g.dfs_step(start="r")', 'g.dfs_step(start="r")'],
         "Right, then fib(0), and back up at fib(3) the right side calls fib(1) again."),
    ],
    "deliver_2": [
        ("b1_explainer_build",
         ["g.reset()", 'g.highlight(nodes=["r"], colour="GOLD")'],
         "Count the work: fib(3) makes two calls, and fib(2) makes two more."),
        ("b2_peer_question",
         ['g.highlight(nodes=["a", "b"], colour="YELLOW")'],
         "For real, why does every call split into two?"),
        ("b3_explainer_feedback",
         ['g.highlight(nodes=["c", "d"], colour="TEAL")'],
         "Because fib(n) adds fib(n minus one) and fib(n minus two), so each call needs both."),
        ("b4_explainer_predict",
         [],
         "Pause: how many calls does fib(3) make in all?"),
        ("b5_peer_build",
         ['g.highlight(nodes=["r", "a", "b", "c", "d"], colour="BLUE")'],
         "Five calls: fib(3), fib(2), fib(0), and fib(1) twice."),
        ("b6_explainer_build",
         ['g.highlight(nodes=["b", "c"], colour="ORANGE")'],
         "Yes, and the repeats are why plain recursion gets slow as n grows."),
    ],
    "end": [
        ("b1_peer_check",
         ['g.path(nodes=["r", "a", "c"], colour="GOLD")'],
         "So a recursion runs down one branch to the bottom before the next."),
        ("b2_explainer_check",
         ['g.highlight(nodes=["b", "c"], colour="ORANGE")'],
         "Exactly, and with no memory it repeats every call it meets twice."),
    ],
}

BOXES_RULES = """\
  - Every step, state or call the lines will name is a box (labels) or a node; label each edge with what moves \
along it (a symbol, yes/no, a probability). A box missing from the picture can't be pointed at later.
  - Let code run the process: dfs_step for the order calls or a depth-first search run, bfs_level for levels, walk \
for a path through a flowchart, feed for a state machine reading its input. The gold marker shows where the \
process is; highlight what the line names.
  - A process that goes on over time (a trajectory S0, A0, R1, S1, ..., a loop unrolled) is a flow of boxes left \
to right, one box per step, so the line can point at each as it comes; a loop of three to five steps is layout \
"circle". Keep the boxes that the idea is about on screen for the whole video.
  - At most three boxes side by side, words short enough for two lines in a box: name the step, not a sentence."""


# --------------------------------------------------------------------------
# Bar charts: counts, distributions, partial sums
# --------------------------------------------------------------------------

_HEADS = ('bars = BarChart(labels=["0", "1", "2"], values=[1, 2, 1], y_label="ways", '
          'title="heads in two flips")')

BARS = {
    "title": "From counting outcomes to expected heads",
    "colour_key": [{"term": "one head", "colour": "GOLD"}, {"term": "average", "colour": "TEAL"}],
    "prepare": [
        ("b1_peer_question",
         [_HEADS],
         "Lowkey, if I flip two coins, how many heads should I expect?"),
        ("b2_explainer_build",
         ['bars.highlight(labels=["1"], colour="GOLD")'],
         "Count the ways first: one head can happen in two different ways."),
    ],
    "initiate": [
        ("b1_peer_question",
         [],
         "Okay, but why count ways instead of just guessing?"),
        ("b2_explainer_objective",
         ["bars.clear()", "bars.total()"],
         "You'll be able to turn counted outcomes into probabilities and an expected value."),
    ],
    "deliver_1": [
        ("b1_explainer_question",
         [],
         "{peer}, are zero, one and two heads equally likely?"),
        ("b2_peer_answer_wrong_idea",
         ['bars.ghost(label="1", value=1, text="all equally likely?")'],
         "Not gonna lie, yes: three results, so each gets one third."),
        ("b3_explainer_feedback",
         ["bars.clear()", 'bars.compare(a="1", b="0")'],
         "No: heads-tails and tails-heads both give one head, so it has two ways."),
        ("b4_peer_build",
         ['bars.highlight(labels=["0", "2"], colour="TEAL")'],
         "So zero heads and two heads each have only one way."),
        ("b5_explainer_build",
         ["bars.clear()", "bars.total()"],
         "Right, four ways in all, and each of the four is equally likely."),
    ],
    "deliver_2": [
        ("b1_explainer_build",
         ["bars.normalize()"],
         "Divide each count by four: that turns ways into probabilities."),
        ("b2_peer_question",
         ['bars.highlight(labels=["1"], colour="GOLD")'],
         "For real, why does one head get half of it?"),
        ("b3_explainer_feedback",
         ['bars.compare(a="1", b="2")'],
         "Because two of the four equally likely ways give one head, and two over four is a half."),
        ("b4_explainer_predict",
         [],
         "Pause: what's the average number of heads?"),
        ("b5_peer_build",
         ["bars.expected()"],
         "One head on average: zero, plus a half, plus two quarters."),
        ("b6_explainer_build",
         ['bars.highlight(labels=["1"], colour="TEAL")'],
         "Yes, the expected value weights each result by its probability, then adds."),
    ],
    "end": [
        ("b1_peer_check",
         ['bars.highlight(labels=["0", "1", "2"], colour="GOLD")'],
         "So I count the ways, divide by the total, and weight each result."),
        ("b2_explainer_check",
         ["bars.expected()"],
         "Exactly: probabilities from counts, and the expected value from those probabilities."),
    ],
}

BARS_RULES = """\
  - Let code compute every number on the bars: series for a sequence (a geometric or discounted one), cumulative \
for partial sums, normalize for counts to probabilities, total, mean_line and expected. Start from the values the \
slide gives and let each step change them on the line that says so.
  - Light up only the bars the line names: during a question, the candidates at most, never every bar.
  - The wrong idea is a ghost bar at the wrong height, on the bar the wrong idea is about.
  - Use the slide's whole set when it fits (up to thirteen bars with one-character names, "T" for ten); if it \
doesn't, the line says the chart shows part of it."""


# --------------------------------------------------------------------------
# Number lines: points, distances, intervals, sequences
# --------------------------------------------------------------------------

_LINE = 'line = NumberLine(x_range=[-3, 7], step=1, title="|x - 2| < 3")'

LINE = {
    "title": "Absolute value is a distance",
    "colour_key": [{"term": "centre", "colour": "GOLD"}, {"term": "solutions", "colour": "TEAL"}],
    "prepare": [
        ("b1_peer_question",
         [_LINE, 'line.point(name="2", x=2, colour="GOLD")'],
         "Lowkey, what does the absolute value of x minus two under three mean?"),
        ("b2_explainer_build",
         ['line.jump(from_x=2, to_x=5, label="+3")'],
         "It asks for every x within three steps of two, on either side."),
    ],
    "initiate": [
        ("b1_peer_question",
         [],
         "Okay, but why picture it on a line?"),
        ("b2_explainer_objective",
         ['line.jump(from_x=2, to_x=-1, label="-3")'],
         "You'll be able to read an absolute value inequality as a distance and solve it."),
    ],
    "deliver_1": [
        ("b1_explainer_question",
         [],
         "{peer}, which numbers make the distance from two under three?"),
        ("b2_peer_answer_wrong_idea",
         ['line.ghost(x=5, text="only x < 5?")'],
         "Not gonna lie, I'd drop the bars and say x below five."),
        ("b3_explainer_feedback",
         ["line.clear()", "line.interval(lo=-1, hi=5, lo_closed=False, hi_closed=False)"],
         "That forgets the left side: a distance counts steps both ways, so x above minus one too."),
        ("b4_peer_build",
         ['line.point(name="x", x=4)'],
         "So four works, because it sits two steps from two."),
        ("b5_explainer_build",
         ['line.point(name="y", x=-2, colour="RED")'],
         "Right, and minus two fails: it is four steps away, more than three."),
    ],
    "deliver_2": [
        ("b1_explainer_build",
         ["line.clear()", 'line.point(name="x", x=6)'],
         "Now test six: is it inside, with a distance from two under three?"),
        ("b2_peer_question",
         ['line.highlight(names=["2"], colour="GOLD")'],
         "For real, why measure from two and not zero?"),
        ("b3_explainer_feedback",
         ['line.jump(from_x=2, to_x=6, label="+4")'],
         "Because x minus two is the gap between x and two, and here that gap is four."),
        ("b4_explainer_predict",
         [],
         "Pause: is six a solution or not?"),
        ("b5_peer_build",
         ["line.interval(lo=-1, hi=5, lo_closed=False, hi_closed=False)"],
         "Not a solution: four is more than three, so six sits outside the band."),
        ("b6_explainer_build",
         ['line.highlight(names=["x"], colour="RED")'],
         "Yes, the solutions are the open stretch from minus one to five."),
    ],
    "end": [
        ("b1_peer_check",
         ['line.highlight(names=["2"], colour="GOLD")'],
         "So an absolute value inequality asks how far x is from a centre."),
        ("b2_explainer_check",
         ['line.jump(from_x=2, to_x=5, label="+3")'],
         "Exactly: within three of two means the interval from minus one to five."),
    ],
}

LINE_RULES = """\
  - Put every number the lines talk about on the line as a named point: the centre, the candidates, the guess. \
A jump (an arc marked +3 or x2) shows a distance or a step; an interval with filled or hollow ends shows a set \
of solutions.
  - A sequence's terms come from its formula (sequence), and how many lie near a limit from band: never type them.
  - The wrong idea is a ghost marker at the wrong number, or the wrong interval."""


# --------------------------------------------------------------------------
# Tables: traces, DP tables, truth tables, counting grids
# --------------------------------------------------------------------------

_TRACE = ('t = Table(columns=["i", "x", "total"], rows=[[1, 4, ""], [2, 1, ""], [3, 3, ""]], '
          'title="total = total + x")')

TABLE = {
    "title": "Tracing a running total, row by row",
    "colour_key": [{"term": "total", "colour": "GOLD"}, {"term": "x", "colour": "TEAL"}],
    "prepare": [
        ("b1_peer_question",
         [_TRACE],
         "Lowkey, how do I know what a loop's variable holds at the end?"),
        ("b2_explainer_build",
         ['t.highlight_col(col=2, colour="GOLD")'],
         "Trace it: one row per pass, and write the total after each pass."),
    ],
    "initiate": [
        ("b1_peer_question",
         [],
         "Okay, but why write a whole table for one loop?"),
        ("b2_explainer_objective",
         ['t.highlight_col(col=1, colour="TEAL")'],
         "You'll be able to trace a loop by hand and predict what it returns."),
    ],
    "deliver_1": [
        ("b1_explainer_question",
         [],
         "{peer}, after all three passes, what does total hold?"),
        ("b2_peer_answer_wrong_idea",
         ['t.ghost(row=2, col=2, value=3, text="just the last x?")'],
         "Not gonna lie, three: total takes the last x it sees."),
        ("b3_explainer_feedback",
         ["t.clear()", "t.fill(row=0, col=2, value=4)"],
         "No: total equals total plus x, so it keeps what it had and adds; first four."),
        ("b4_peer_build",
         ["t.depends(cell=[1, 2], on=[[0, 2], [1, 1]])", "t.fill(row=1, col=2, value=5)"],
         "So the second pass adds one to four, and total becomes five."),
        ("b5_explainer_build",
         ['t.highlight(cells=[[1, 2]], colour="GOLD")'],
         "Right, each row's total is the row above's total plus this row's x."),
    ],
    "deliver_2": [
        ("b1_explainer_build",
         ["t.clear()", 't.highlight_row(row=2, colour="TEAL")'],
         "Last pass: i is three, x is three, and total starts at five."),
        ("b2_peer_question",
         ['t.highlight(cells=[[1, 2]], colour="GOLD")'],
         "For real, why does it start at five and not zero?"),
        ("b3_explainer_feedback",
         ["t.depends(cell=[2, 2], on=[[1, 2], [2, 1]])"],
         "Because the loop never resets total: each pass begins with the last pass's result."),
        ("b4_explainer_predict",
         [],
         "Pause: what is total after this pass?"),
        ("b5_peer_build",
         ["t.fill(row=2, col=2, value=8)"],
         "Eight: five plus three, so the loop returns eight."),
        ("b6_explainer_build",
         ['t.highlight(cells=[[2, 2]], colour="GOLD")'],
         "Yes, and eight is four plus one plus three: the sum of every x."),
    ],
    "end": [
        ("b1_peer_check",
         ['t.highlight_col(col=2, colour="GOLD")'],
         "So a trace writes each variable after every pass, one row at a time."),
        ("b2_explainer_check",
         ['t.highlight(cells=[[2, 2]], colour="GOLD")'],
         "Exactly, and the last row of the trace is what the loop returns."),
    ],
}

TABLE_RULES = """\
  - Draw the slide's table at its real size when it fits (seven columns, eight rows; drop row_labels if the \
cells get tight). A trace has one column per variable and one row per pass or step.
  - A table built from a rule (Pascal's triangle, grid paths, Fibonacci, a truth table) is filled by fill_next or \
fill_row, never typed; for a trace, fill each value on the line that works it out, and depends draws arrows from \
the cells it came from.
  - The wrong idea is the wrong value in its empty cell (ghost), so the next line can fill the right one."""


# --------------------------------------------------------------------------
# Plots: functions, growth curves, data, polar and parametric curves
# --------------------------------------------------------------------------

_GROWTH = ('plot = FunctionPlot(x_range=[1, 10], y_range=[0, 100], x_label="n", y_label="steps", '
           'curves=[{"name": "n", "fn": "n", "colour": "BLUE"}], title="steps for n items")')

PLOT = {
    "title": "Why n squared outgrows n",
    "colour_key": [{"term": "n", "colour": "BLUE"}, {"term": "n squared", "colour": "ORANGE"}],
    "prepare": [
        ("b1_peer_question",
         [_GROWTH],
         "Lowkey, why is an n squared algorithm such a big deal?"),
        ("b2_explainer_build",
         ['plot.plot(name="n^2", fn="n**2", colour="ORANGE")'],
         "Its steps grow with n times n, so they climb far faster than n."),
    ],
    "initiate": [
        ("b1_peer_question",
         [],
         "Okay, but why compare curves instead of single numbers?"),
        ("b2_explainer_objective",
         ['plot.dot(curve="n^2", x=5, label="25")'],
         "You'll be able to compare how two running times grow as the input gets bigger."),
    ],
    "deliver_1": [
        ("b1_explainer_question",
         [],
         "{peer}, how much slower is n squared than n?"),
        ("b2_peer_answer_wrong_idea",
         ['plot.ghost(fn="2*n", text="just twice as slow?")'],
         "Not gonna lie, about twice as slow, like two n."),
        ("b3_explainer_feedback",
         ["plot.clear()", 'plot.dot(curve="n^2", x=10, label="100")'],
         "No: the gap isn't a fixed factor, because at ten items n squared already takes a hundred."),
        ("b4_peer_build",
         ['plot.dot(curve="n", x=10, label="10")'],
         "So at ten items, n takes ten steps and n squared a hundred."),
        ("b5_explainer_build",
         ['plot.highlight(curve="n^2", colour="ORANGE")'],
         "Right, the ratio is n itself, so the gap keeps growing with the input."),
    ],
    "deliver_2": [
        ("b1_explainer_build",
         ["plot.clear()", 'plot.dot(curve="n^2", x=4, label="16")'],
         "Take four items: n squared needs sixteen steps, n needs four."),
        ("b2_peer_question",
         ['plot.dot(curve="n", x=4, label="4")'],
         "For real, why does doubling the items hurt so much?"),
        ("b3_explainer_feedback",
         ['plot.dot(curve="n^2", x=2, label="4")'],
         "Because n times n doubles twice: two items take four steps, four take sixteen."),
        ("b4_explainer_predict",
         [],
         "Pause: how many steps for eight items?"),
        ("b5_peer_build",
         ['plot.dot(curve="n^2", x=8, label="64")'],
         "Sixty-four: sixteen times four, since eight is four doubled."),
        ("b6_explainer_build",
         ['plot.vline(x=8)'],
         "Yes, doubling n quadruples n squared, while n itself only doubles."),
    ],
    "end": [
        ("b1_peer_check",
         ['plot.highlight(curve="n^2", colour="ORANGE")'],
         "So n squared pulls away from n, and the gap grows with n."),
        ("b2_explainer_check",
         ['plot.dot(curve="n^2", x=10, label="100")'],
         "Exactly: double the input, and an n squared algorithm takes four times the steps."),
    ],
}

PLOT_RULES = """\
  - Plot every curve the lines compare, and mark each number a line says as a dot on its curve with a label \
(dot, dot_t), so the viewer reads the value off the picture. Points come from the curve's formula: never type a \
y value.
  - A tangent shows a slope or a rate; shade an area; peak a maximum; a polar or parametric curve and sector for \
polar ideas; points with labels and equal_scale for the complex plane or geometry.
  - The wrong idea is a ghost curve: the curve the wrong idea predicts, so the feedback line can set the real one \
beside it."""


# --------------------------------------------------------------------------
# Formulas: derivations, identities, proofs
# --------------------------------------------------------------------------

FORMULAS = {
    "title": "Why (a + b) squared has a middle term",
    "colour_key": [{"term": "middle term", "colour": "ORANGE"}, {"term": "squares", "colour": "BLUE"}],
    "prepare": [
        ("b1_peer_question",
         ['eq = EquationSteps(tex="(a + b)^2")'],
         "Lowkey, why isn't a plus b, all squared, just a squared plus b squared?"),
        ("b2_explainer_build",
         ['eq.then(tex="(a + b)^2 = (a + b)(a + b)")'],
         "Squaring means multiplying the bracket by itself, so every part meets every part."),
    ],
    "initiate": [
        ("b1_peer_question",
         [],
         "Okay, but why does that one step matter so much?"),
        ("b2_explainer_objective",
         ['eq.highlight(part="(a + b)(a + b)", colour="BLUE")'],
         "You'll be able to expand a squared bracket and spot the term people forget."),
    ],
    "deliver_1": [
        ("b1_explainer_question",
         [],
         "{peer}, what do you get when you expand it?"),
        ("b2_peer_answer_wrong_idea",
         ['eq.then(tex="(a + b)^2 = a^2 + b^2")'],
         "Not gonna lie, I'd square each one: a squared plus b squared."),
        ("b3_explainer_feedback",
         ["eq.cross_out()", 'eq.then(tex="a \\cdot a + a \\cdot b + b \\cdot a + b \\cdot b")'],
         "That skips the cross terms: each a meets each b, so there are four products."),
        ("b4_peer_build",
         ['eq.highlight(part="a \\cdot b + b \\cdot a", colour="ORANGE")'],
         "So a times b shows up twice, once from each bracket."),
        ("b5_explainer_build",
         ['eq.then(tex="(a + b)^2 = a^2 + 2ab + b^2")', "eq.box()"],
         "Right, the two cross terms make the middle term, two a b."),
    ],
    "deliver_2": [
        ("b1_explainer_build",
         ['eq.then(tex="(3 + 1)^2 = 3^2 + 2 \\cdot 3 \\cdot 1 + 1^2")'],
         "Check it with three and one: four squared should come out to sixteen."),
        ("b2_peer_question",
         ['eq.highlight(part="2 \\cdot 3 \\cdot 1", colour="ORANGE")'],
         "For real, why should the middle part be six?"),
        ("b3_explainer_feedback",
         ['eq.colour(part="3^2", colour="BLUE")'],
         "Because two times three times one is six: the three meets the one twice."),
        ("b4_explainer_predict",
         ['eq.then(tex="9 + 6 + 1 = ?")', 'eq.cover(part="?")'],
         "Pause: what do nine, six and one add to?"),
        ("b5_peer_build",
         ["eq.uncover()", 'eq.rewrite(tex="9 + 6 + 1 = 16")'],
         "Sixteen, the same as four squared, so the middle term was needed."),
        ("b6_explainer_build",
         ["eq.box()"],
         "Yes, without the six we'd get ten, and four squared is not ten."),
    ],
    "end": [
        ("b1_peer_check",
         ['eq.highlight(part="9 + 6 + 1", colour="ORANGE")'],
         "So squaring a sum adds a middle term, two times the product."),
        ("b2_explainer_check",
         ['eq.colour(part="16", colour="BLUE")'],
         "Exactly: a plus b squared is a squared, plus two a b, plus b squared."),
    ],
}

FORMULAS_RULES = """\
  - Every step the lines work through is written as it is said: then for a new line, rewrite to change the \
current one, highlight or colour the piece the line names, box the result. A line that derives over an unchanged \
formula scores as text.
  - Check a general result with the slide's numbers in a line of its own, and cover the piece a predict line asks \
for (cover, then uncover on the answer).
  - The wrong idea is the wrong step written out, then crossed out (cross_out), and the right step under it.
  - Keep each formula short (about twenty symbols): one step per line, not the whole derivation at once."""


# --------------------------------------------------------------------------
# Data structures, each with its own worked example
# --------------------------------------------------------------------------

_SHARED_DS_RULES = """\
  - Draw the structure itself, not a list of cells standing in for it, and run every operation with its computed \
action: the picture then shows what the operation really does, and its sentence names the values.
  - A predict line asks for the next state before the step that shows it (where a key lands, what pop returns, \
the next node visited): put the step on the answer line, never during the objective or the question.
  - The wrong idea is the wrong link, end, bucket or place, drawn as a ghost on a free spot."""

_REVERSE = 'lst = LinkedList(values=[4, 7, 2], title="reverse in place")'

LINKED = {
    "title": "Reversing a linked list in place",
    "colour_key": [{"term": "reversed", "colour": "TEAL"}, {"term": "curr", "colour": "GOLD"}],
    "prepare": [
        ("b1_peer_question", [_REVERSE],
         "Lowkey, how do you flip a linked list without making a new one?"),
        ("b2_explainer_build", ['lst.point(name="curr", index=0)'],
         "You walk it once with curr and turn each node's arrow around."),
    ],
    "initiate": [
        ("b1_peer_question", [],
         "Okay, but why not just copy it backwards?"),
        ("b2_explainer_objective", ['lst.highlight(indices=[0, 1, 2], colour="TEAL")'],
         "You'll be able to reverse a linked list in place, with only two pointers."),
    ],
    "deliver_1": [
        ("b1_explainer_question", [],
         "{peer}, what happens when we flip four's arrow first?"),
        ("b2_peer_answer_wrong_idea", ['lst.ghost(from_index=0, to_index=None, text="the rest is lost?")'],
         "Not gonna lie, we'd lose seven and two the moment four points back."),
        ("b3_explainer_feedback", ["lst.clear()", "lst.reverse_step()"],
         "No, because curr moves on to seven first, so the rest is never lost."),
        ("b4_peer_build", ["lst.reverse_step()"],
         "So seven's arrow now points back to four, and curr moves to two."),
        ("b5_explainer_build", ['lst.highlight(indices=[0, 1], colour="TEAL")'],
         "Right: everything behind curr is already reversed, one link at a time."),
    ],
    "deliver_2": [
        ("b1_explainer_build", ['lst.highlight(indices=[2], colour="GOLD")'],
         "Now curr is at two, the last node, and prev holds seven."),
        ("b2_peer_question", [],
         "For real, why keep prev around at all?"),
        ("b3_explainer_feedback", ['lst.highlight(indices=[1], colour="YELLOW")'],
         "Because two must point back to something, and prev says where: seven."),
        ("b4_explainer_predict", [],
         "Pause: after this last flip, where does head go?"),
        ("b5_peer_build", ["lst.reverse_step()"],
         "Head moves to two, so the list reads two, seven, four."),
        ("b6_explainer_build", ['lst.point(name="curr", index=None)'],
         "Yes, and curr is null now, which is how the loop knows to stop."),
    ],
    "end": [
        ("b1_peer_check", ['lst.highlight(indices=[0, 1, 2], colour="TEAL")'],
         "So I walk once, flip each arrow back, and move head to the end."),
        ("b2_explainer_check", ['lst.point(name="prev", index=2)'],
         "Exactly: one pass, two pointers, and every link turned around in place."),
    ],
}

LINKED_RULES = _SHARED_DS_RULES + """
  - Name the pointers as the code does (head, curr, prev) and show what they hold: insert and delete show the \
relinking in order, reverse_step flips one link per line, find_step moves curr one node per line."""

_BRACKETS = 'st = StackQueue(kind="stack", title="( [ ] ) balanced?")'

STACK = {
    "title": "Checking brackets with a stack",
    "colour_key": [{"term": "top", "colour": "GOLD"}, {"term": "mismatch", "colour": "RED"}],
    "prepare": [
        ("b1_peer_question", [_BRACKETS],
         "Lowkey, how does a computer know if brackets are balanced?"),
        ("b2_explainer_build", ['st.push(value="(")'],
         "It keeps a stack, and every opening bracket is pushed on top."),
    ],
    "initiate": [
        ("b1_peer_question", [],
         "Okay, but why a stack and not a queue?"),
        ("b2_explainer_objective", ["st.peek()"],
         "You'll be able to check brackets by matching each closer with the top."),
    ],
    "deliver_1": [
        ("b1_explainer_question", [],
         "{peer}, a square bracket opens next. Which one closes first?"),
        ("b2_peer_answer_wrong_idea", ['st.ghost(end="bottom", text="the oldest closes first?")'],
         "Not gonna lie, the round one, because it opened first."),
        ("b3_explainer_feedback", ["st.clear()", 'st.push(value="[")'],
         "No: the square one is newest, so it is pushed on top and must close first."),
        ("b4_peer_build", ["st.pop()"],
         "So the closing square bracket pops the top, and they match."),
        ("b5_explainer_build", ["st.peek()"],
         "Right, and now the round bracket is back on top, waiting."),
    ],
    "deliver_2": [
        ("b1_explainer_build", ['st.highlight(positions=[0], colour="GOLD")'],
         "Next comes a closing round bracket, and it checks the top: round."),
        ("b2_peer_question", [],
         "For real, what if the top didn't match?"),
        ("b3_explainer_feedback", ['st.ghost(end="top", text="mismatch: broken")'],
         "Then the brackets are broken right there, since the newest opener must close first."),
        ("b4_explainer_predict", [],
         "Pause: what's left once this bracket closes?"),
        ("b5_peer_build", ["st.clear()", "st.pop()"],
         "Nothing: it pops the round bracket off, and the stack is empty."),
        ("b6_explainer_build", ['st.push(value="(")'],
         "Yes, empty means balanced; a leftover opener pushed like this means not."),
    ],
    "end": [
        ("b1_peer_check", ['st.highlight(positions=[0], colour="RED")'],
         "So openers go on top, closers pop a match, and the end must be empty."),
        ("b2_explainer_check", ["st.pop()"],
         "Exactly: the last opener in is always the first one to close, off the top."),
    ],
}

STACK_RULES = _SHARED_DS_RULES + """
  - A stack's top and a queue's front and rear are where every line looks: push and pop (enqueue and dequeue) on \
the line that says them, peek to point at what comes out next. Comparing a stack and a queue: draw both."""

_PROBE = 'ht = HashTable(size=7, mode="probing", keys=[10, 3], title="h(k) = k mod 7")'

HASH = {
    "title": "Collisions and linear probing",
    "colour_key": [{"term": "collision", "colour": "GOLD"}, {"term": "cluster", "colour": "ORANGE"}],
    "prepare": [
        ("b1_peer_question", [_PROBE],
         "Lowkey, what happens when two keys want the same bucket?"),
        ("b2_explainer_build", ['ht.highlight(buckets=[3, 4], colour="GOLD")'],
         "Ten and three both hash to bucket three, so three moved to four."),
    ],
    "initiate": [
        ("b1_peer_question", [],
         "Okay, but why not just use a bigger table?"),
        ("b2_explainer_objective", ["ht.load()"],
         "You'll be able to place keys with linear probing and count each lookup's checks."),
    ],
    "deliver_1": [
        ("b1_explainer_question", [],
         "{peer}, seventeen mod seven is three. Where does seventeen go?"),
        ("b2_peer_answer_wrong_idea", ['ht.ghost(key=17, bucket=3, text="share bucket 3?")'],
         "Not gonna lie, into bucket three, right next to ten."),
        ("b3_explainer_feedback", ["ht.clear()", "ht.insert(key=17)"],
         "No, one bucket holds one key here, so seventeen probes three, four, then five."),
        ("b4_peer_build", ['ht.highlight(buckets=[5], colour="GOLD")'],
         "So it lands in bucket five, after two taken buckets."),
        ("b5_explainer_build", ['ht.highlight(buckets=[3, 4, 5], colour="ORANGE")'],
         "Right: keys that collide pile up side by side in one cluster."),
    ],
    "deliver_2": [
        ("b1_explainer_build", ["ht.clear()", "ht.insert(key=24)"],
         "Twenty-four hashes to three as well, so it slides down to six."),
        ("b2_peer_question", ['ht.highlight(buckets=[3], colour="GOLD")'],
         "For real, how does a lookup find it again?"),
        ("b3_explainer_feedback", ['ht.highlight(buckets=[3, 4, 5, 6], colour="YELLOW")'],
         "Because find walks the same path: start at its hash, move down until it matches."),
        ("b4_explainer_predict", [],
         "Pause: how many checks to find twenty-four?"),
        ("b5_peer_build", ["ht.clear()", "ht.find(key=24)"],
         "Four checks: three, four, five, then six, where it sits."),
        ("b6_explainer_build", ["ht.load()"],
         "Yes, and as the table fills, those runs grow, so lookups slow down."),
    ],
    "end": [
        ("b1_peer_check", ['ht.highlight(buckets=[3, 4, 5, 6], colour="ORANGE")'],
         "So a collision moves the key down, and find follows the same steps."),
        ("b2_explainer_check", ["ht.find(key=10)"],
         "Exactly, which is why a low load factor keeps every lookup short to find."),
    ],
}

HASH_RULES = _SHARED_DS_RULES + """
  - Every insert and find shows its hash and the buckets it tries; use the slide's hash (a and b: h(k) = (a k + b) \
mod m; a = 0 is a bad hash that piles every key into one chain). Collisions are the point: pick keys that collide."""

_BST = 't = BinaryTree(kind="bst", values=[50, 30, 70, 20, 40], title="where does 65 go?")'

TREE = {
    "title": "Inserting and searching in a BST",
    "colour_key": [{"term": "path", "colour": "YELLOW"}, {"term": "new value", "colour": "GOLD"}],
    "prepare": [
        ("b1_peer_question", [_BST],
         "Lowkey, how does a search tree stay sorted when new values arrive?"),
        ("b2_explainer_build", ['t.highlight(values=[30, 20, 40], colour="TEAL")'],
         "Everything left of a node is smaller, and everything right is bigger."),
    ],
    "initiate": [
        ("b1_peer_question", [],
         "Okay, but why does that order matter so much?"),
        ("b2_explainer_objective", ["t.search(value=40)"],
         "You'll be able to insert and search by comparing down from the root."),
    ],
    "deliver_1": [
        ("b1_explainer_question", [],
         "{peer}, where should sixty-five go in this tree?"),
        ("b2_peer_answer_wrong_idea", ['t.ghost(parent=20, side="left", value=65, text="first free spot?")'],
         "Not gonna lie, the first free spot, under twenty on the left."),
        ("b3_explainer_feedback", ["t.clear()", "t.insert(value=65)"],
         "No, that breaks the order: sixty-five beats fifty, so it goes right."),
        ("b4_peer_build", ['t.highlight(values=[70], colour="YELLOW")'],
         "Then sixty-five is smaller than seventy, so it goes left of seventy."),
        ("b5_explainer_build", ['t.highlight(values=[65], colour="GOLD")'],
         "Right, one comparison per level, and it lands in the only place that fits."),
    ],
    "deliver_2": [
        ("b1_explainer_build", ["t.clear()", 't.highlight(values=[50], colour="GOLD")'],
         "Now search for forty-five, starting at the root, fifty, like before."),
        ("b2_peer_question", [],
         "For real, how do we know when to stop looking?"),
        ("b3_explainer_feedback", ['t.highlight(values=[30, 40], colour="YELLOW")'],
         "We stop when we match, or when the side we need has no child."),
        ("b4_explainer_predict", [],
         "Pause: is forty-five in this tree?"),
        ("b5_peer_build", ["t.clear()", "t.search(value=45)"],
         "No: left at fifty, right at thirty, right at forty, and it runs out."),
        ("b6_explainer_build", ['t.highlight(values=[50, 30, 40], colour="TEAL")'],
         "Yes, three comparisons for a tree three levels deep, never more."),
    ],
    "end": [
        ("b1_peer_check", ['t.highlight(values=[20, 30, 40, 50, 65, 70], colour="TEAL")'],
         "So I compare down from the root, left if smaller, right if bigger."),
        ("b2_explainer_check", ['t.highlight(values=[50], colour="GOLD")'],
         "Exactly, and the same path tells you where to insert or where to stop."),
    ],
}

TREE_RULES = _SHARED_DS_RULES + """
  - A BST's insert, search and delete light their path from the root; a heap keeps its array under the tree (the \
array is how it is stored) and push, pop and heapify swap in both; traverse_step visits one node per line.
  - Build the tree the slide uses (BST: insert a middle value first, or it grows lopsided; at most five levels)."""

_DIJKSTRA = ('g = Graph(nodes=["S", "A", "B", "C"], edges=[["S", "A", "4"], ["S", "B", "1"], ["B", "A", "2"], '
             '["A", "C", "1"], ["B", "C", "5"]], title="shortest paths from S")')

GRAPH_ALGOS = {
    "title": "Dijkstra settles the closest first",
    "colour_key": [{"term": "settled", "colour": "TEAL"}, {"term": "detour", "colour": "YELLOW"}],
    "prepare": [
        ("b1_peer_question", [_DIJKSTRA],
         "Lowkey, how does a map app find the shortest route?"),
        ("b2_explainer_build", ['g.highlight(nodes=["S"], colour="GOLD")'],
         "It grows outward from the start, always settling the closest place first."),
    ],
    "initiate": [
        ("b1_peer_question", [],
         "Okay, but why not just take the fewest roads?"),
        ("b2_explainer_objective", ['g.dijkstra_step(start="S")'],
         "You'll be able to run Dijkstra by hand and read off each shortest distance."),
    ],
    "deliver_1": [
        ("b1_explainer_question", [],
         "{peer}, A is four away. Is four its shortest distance?"),
        ("b2_peer_answer_wrong_idea", ['g.ghost_edge(a="S", b="A", text="4 is final?")'],
         "Not gonna lie, yes: the direct road is four, so that's it."),
        ("b3_explainer_feedback", ['g.dijkstra_step(start="S")'],
         "No, B is only one away, so we settle B first and look through it."),
        ("b4_peer_build", ['g.highlight_edge(a="B", b="A", colour="YELLOW")'],
         "So going through B, A costs one plus two, which is three."),
        ("b5_explainer_build", ['g.dijkstra_step(start="S")'],
         "Right, the detour is shorter than the direct road, so A settles next."),
    ],
    "deliver_2": [
        ("b1_explainer_build", ['g.highlight(nodes=["C"], colour="GOLD")'],
         "Last is C, and settling A just gave it a cheaper route."),
        ("b2_peer_question", [],
         "For real, why does settling A change C?"),
        ("b3_explainer_feedback", ['g.highlight_edge(a="A", b="C", colour="YELLOW")'],
         "Because A's edge to C costs one, so three plus one beats the old route."),
        ("b4_explainer_predict", [],
         "Pause: what's C's shortest distance?"),
        ("b5_peer_build", ['g.dijkstra_step(start="S")'],
         "Four: three to reach A, plus one more to C."),
        ("b6_explainer_build", ['g.path(nodes=["S", "B", "A", "C"], colour="TEAL")'],
         "Yes, so the shortest path runs S, B, A, C, not the direct roads."),
    ],
    "end": [
        ("b1_peer_check", ['g.highlight(nodes=["S", "B", "A", "C"], colour="TEAL")'],
         "So Dijkstra settles the closest open place, then updates its neighbours."),
        ("b2_explainer_check", ['g.path(nodes=["S", "B", "A"], colour="GOLD")'],
         "Exactly: once settled, a distance never shrinks, because every weight is positive."),
    ],
}

GRAPH_ALGOS_RULES = """\
  - Run the algorithm with its computed step, one per line: dfs_step, bfs_level, dijkstra_step (distances appear \
beside the nodes, relaxed edges light up), prim_step, kruskal_step, topo_step. Give every edge a weight (the third \
item) for Dijkstra, Prim and Kruskal; a topological order needs a directed graph.
  - Pick a small graph from the slides where the idea shows: a detour shorter than the direct edge (Dijkstra), an \
edge skipped because it closes a cycle (Kruskal). A line that works out a distance says the sum ("one plus two").
  - A predict line asks for the next distance or node before the step that settles it."""


MODULES: dict[str, Module] = {m.name: m for m in (
    Module("boxes", frozenset({"flowchart", "call_tree", "state_machine"}),
           "Recursion: the calls fib(3) makes, and why fib(1) is worked out twice", BOXES, BOXES_RULES),
    Module("bars", frozenset({"bar_meter", "probability", "series"}),
           "Expected value: counting outcomes, turning them into probabilities, weighting them", BARS, BARS_RULES),
    Module("number_line", frozenset({"number_line"}),
           "Absolute value inequalities: |x - 2| < 3 as a distance on the number line", LINE, LINE_RULES),
    Module("table", frozenset({"dp_table", "code_trace", "bits_logic", "counting"}),
           "Tracing a loop: what a running total holds after each pass", TABLE, TABLE_RULES),
    Module("plot", frozenset({"function_plot", "growth_curves", "stats_plots", "ml_basics", "polar_parametric",
                              "complex_plane"}),
           "Growth of running time: why n squared outgrows n", PLOT, PLOT_RULES),
    Module("formulas", frozenset({"equation_steps", "proof_steps", "matrix_ops"}),
           "Expanding (a + b) squared: where the middle term 2ab comes from", FORMULAS, FORMULAS_RULES),
    Module("linked_list", frozenset({"linked_list"}),
           "Reversing a linked list in place: prev and curr, one link at a time", LINKED, LINKED_RULES),
    Module("stack_queue", frozenset({"stack_queue"}),
           "Stacks in use: checking that brackets are balanced", STACK, STACK_RULES),
    Module("hash_table", frozenset({"hash_table"}),
           "Hash tables: collisions under linear probing, and the checks a lookup makes", HASH, HASH_RULES),
    Module("tree", frozenset({"tree"}),
           "Binary search trees: inserting and searching by comparing down from the root", TREE, TREE_RULES),
    Module("graph_algorithms", frozenset({"graph"}),
           "Dijkstra's algorithm: settling the closest node first, and a detour that beats the direct edge",
           GRAPH_ALGOS, GRAPH_ALGOS_RULES),
)}


def module_for(family: str | None) -> Module | None:
    """The module for a picture family, or None (the prompt stays as it was)."""
    return next((m for m in MODULES.values() if family in m.families), None)


def render_module_example(module: Module, *, explainer: str, peer: str) -> str:
    """The module's example as the prompt shows it, in the same form as storyboard_example.render_example."""
    ex = module.example
    lines = [f"Knowledge Unit: {module.ku}", f"title: {ex['title']}",
             "colour_key: " + ", ".join(f"{t['term']} = {t['colour']}" for t in ex["colour_key"])]
    for key in SEGMENT_KEYS:
        lines.append(f"{key}:")
        for field, draw, narration in ex[key]:
            lines.append(f"  {field}:")
            lines.append(f"    draw: {draw}")
            lines.append(f"    narration: {narration.format(explainer=explainer, peer=peer)}")
    return "\n".join(lines) + "\n"


def module_rules(module: Module) -> str:
    """The module's rules as a prompt section."""
    return f"Drawing this kind of picture ({module.name.replace('_', ' ')})\n{module.rules}\n\n"


__all__ = ["MODULES", "Module", "module_for", "module_rules", "render_module_example"]
