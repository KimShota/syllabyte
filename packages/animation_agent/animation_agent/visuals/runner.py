"""
Plays a segment's template calls inside a GridLayoutScene, one beat at a time.

The calls were checked when the script was written (calls.check_segment); they are parsed and checked again
here, so a scene file can't run anything else. Each beat's actions share BEAT_FILL of the beat's narration
time, in proportion to how long each takes by default (Template.durations), and never run longer than that
default. end_beat (called by the scene) then waits out the rest of the sentence.
"""

from __future__ import annotations

import sys

from manim import FadeOut

from animation_agent.visuals.array_bars import ArrayBars
from animation_agent.visuals.bar_chart import BarChart
from animation_agent.visuals.base import Template
from animation_agent.visuals.calls import CallError, parse_call, parse_segment
from animation_agent.visuals.equation_steps import EquationSteps
from animation_agent.visuals.function_plot import FunctionPlot
from animation_agent.visuals.graph import Graph
from animation_agent.visuals.linear_map import LinearMap2D
from animation_agent.visuals.merge_sort import MergeSort
from animation_agent.visuals.note import Note
from animation_agent.visuals.number_line import NumberLine
from animation_agent.visuals.specs import REGISTRY
from animation_agent.visuals.table import Table

CLASSES: dict[str, type[Template]] = {cls.spec.name: cls for cls in (
    ArrayBars, MergeSort, Graph, BarChart, NumberLine, Table, FunctionPlot, LinearMap2D, EquationSteps, Note)}
assert set(CLASSES) == set(REGISTRY), "every spec needs a drawing class"

BEAT_FILL = 0.8  # share of a beat's narration the animations may take
MIN_STEP = 0.1


class SpecRunner:
    def __init__(self, scene, draws: list[list[str]] | None = None, carried: list[str] | None = None):
        self.scene = scene
        self.objects: dict[str, Template] = {}
        self.templates_of: dict[str, str] = {}
        self.carried = list(carried or [])
        # Which actions the segment calls on each name (with the calls carried in), so a template only makes
        # room for what it will show.
        self.uses: dict[str, set[str]] | None = {} if draws or carried else None
        for beat in parse_segment([self.carried, *(draws or [])]) if self.uses is not None else []:
            for call in beat:
                if call.action is not None:
                    self.uses.setdefault(call.target, set()).add(call.action)  # type: ignore[union-attr]

    def setup(self) -> None:
        """Puts on screen what the segments before this one left there: replays their calls (`carried`) at once,
        without playing them, so beat 1 starts from the picture the last segment ended on."""
        for text in self.carried:
            call = parse_call(text, self.templates_of)
            if call.action is None:
                self.templates_of[call.target] = call.template
            self._run(call, 0.0, instant=True)

    def beat(self, n: int, texts: list[str]) -> None:
        calls = []
        for t in texts:
            call = parse_call(t, self.templates_of)
            if call.action is None:
                self.templates_of[call.target] = call.template
            calls.append(call)
        if not calls:
            return
        durations = [CLASSES[c.template].duration(c.action) for c in calls]
        budget = BEAT_FILL * self.scene.beat_durations[n - 1]
        scale = min(1.0, budget / sum(durations))
        for call, duration in zip(calls, durations):
            self._run(call, duration * scale)

    def _run(self, call, seconds: float, instant: bool = False) -> None:
        """Plays one call. An action that fails is skipped, not fatal: the segment then misses one highlight
        instead of falling back to LLM-written code, and, because later segments replay this one's calls, so do
        they (runs/course-test-1: one failed highlight sent all five segments of a video to code). A create that
        fails still fails the segment, since nothing after it could draw."""
        if call.action is None:
            self._play(call, seconds, instant)
            return
        try:
            self._play(call, seconds, instant)
        except Exception as e:  # noqa: BLE001 - any drawing error: skip the call, keep the picture
            print(f"[spec] skipped {call.target}.{call.action}: {type(e).__name__}: {e}", file=sys.stderr,
                  flush=True)
            self._tidy()

    def _play(self, call, seconds: float, instant: bool) -> None:
        spec = REGISTRY[call.template]
        if call.action is None:
            if (old := self.objects.pop(call.target, None)) is not None:  # creating a name again replaces it
                if instant:
                    self._forget(old)
                else:
                    self.scene.play(FadeOut(old.group), run_time=max(MIN_STEP, 0.25 * seconds))
                    self._forget(old)
                    seconds *= 0.75
            uses = None if self.uses is None else self.uses.get(call.target, set())
            obj = CLASSES[call.template](self.scene, spec.params.model_validate(call.args), uses)
            self.objects[call.target] = obj
            self.scene.add(obj.group)
            steps = obj.create()
        else:
            obj = self.objects.get(call.target)
            if obj is None:
                raise CallError(f"{call.target} was removed")
            args = spec.all_actions()[call.action].args.model_validate(call.args)
            steps = getattr(obj, call.action)(args)
        for step in steps:
            if instant:
                self._apply(step.anims)
            else:
                self.scene.play(*step.anims, run_time=max(MIN_STEP, step.share * seconds))
            self._tidy()
        if call.action == "remove":
            self._forget(self.objects.pop(call.target))

    def _apply(self, anims) -> None:
        """A step's end state without playing it (Scene.play's begin and finish, with no frames between)."""
        if not anims:
            return
        anims = self.scene.compile_animations(*anims)
        self.scene.add_mobjects_from_animations(anims)
        for anim in anims:
            anim._setup_scene(self.scene)
            anim.begin()
        for anim in anims:
            anim.finish()
            anim.clean_up_from_scene(self.scene)

    def _tidy(self) -> None:
        """Animating a part (FadeIn, .animate) adds it to the scene on its own as well as through its template's
        group; drop those extra top-level entries, so a part removed from its group later doesn't linger."""
        parts = {id(m) for obj in self.objects.values() for m in obj.group.get_family()[1:]}
        self.scene.mobjects[:] = [m for m in self.scene.mobjects if id(m) not in parts]
        for obj in self.objects.values():
            if obj.group not in self.scene.mobjects:
                self.scene.mobjects.append(obj.group)

    def _forget(self, obj: Template) -> None:
        family = {id(m) for m in obj.group.get_family()}
        self.scene.mobjects[:] = [m for m in self.scene.mobjects if id(m) not in family]
