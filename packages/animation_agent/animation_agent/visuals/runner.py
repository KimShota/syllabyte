"""
Plays a segment's template calls inside a GridLayoutScene, one beat at a time.

The calls were checked when the script was written (calls.check_segment); they are parsed and checked again
here, so a scene file can't run anything else. Each beat's actions share BEAT_FILL of the beat's narration
time, in proportion to how long each takes by default (Template.durations), and never run longer than that
default. end_beat (called by the scene) then waits out the rest of the sentence.
"""

from __future__ import annotations

from animation_agent.visuals.array_bars import ArrayBars
from animation_agent.visuals.base import Template
from animation_agent.visuals.calls import CallError, parse_call, parse_segment
from animation_agent.visuals.equation_steps import EquationSteps
from animation_agent.visuals.linear_map import LinearMap2D
from animation_agent.visuals.note import Note
from animation_agent.visuals.specs import REGISTRY

CLASSES: dict[str, type[Template]] = {cls.spec.name: cls for cls in (ArrayBars, LinearMap2D, EquationSteps, Note)}
assert set(CLASSES) == set(REGISTRY), "every spec needs a drawing class"

BEAT_FILL = 0.8  # share of a beat's narration the animations may take
MIN_STEP = 0.1


class SpecRunner:
    def __init__(self, scene, draws: list[list[str]] | None = None):
        self.scene = scene
        self.objects: dict[str, Template] = {}
        self.templates_of: dict[str, str] = {}
        # Which actions the segment calls on each name, so a template only makes room for what it will show.
        self.uses: dict[str, set[str]] | None = {} if draws else None
        for beat in parse_segment(draws) if draws else []:
            for call in beat:
                if call.action is not None:
                    self.uses.setdefault(call.target, set()).add(call.action)  # type: ignore[union-attr]

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

    def _run(self, call, seconds: float) -> None:
        spec = REGISTRY[call.template]
        if call.action is None:
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
            self.scene.play(*step.anims, run_time=max(MIN_STEP, step.share * seconds))
            self._tidy()
        if call.action == "remove":
            self._forget(self.objects.pop(call.target))

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
