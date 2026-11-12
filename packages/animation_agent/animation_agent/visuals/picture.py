"""Picture: a picture program's snapshots (scene/), drawn in the template's area, one step() at a time."""

from __future__ import annotations

from animation_agent.scene.draw import PictureRunner
from animation_agent.visuals.base import Step, Steps, Template
from animation_agent.visuals.specs import PICTURE, picture_snapshots, snapshot_index


class Picture(Template):
    spec = PICTURE
    durations = {"create": 0.8, "step": 1.0, "show": 1.0}

    def create(self) -> Steps:
        box = self.bounds
        self.runner = PictureRunner(self.scene, picture_snapshots(self.p.program),
                                    (box.width, box.height, box.top), self.group)
        self.at = 0
        self.snaps = self.runner.snaps
        yield Step(self.runner.changes(0))

    def show(self, a) -> Steps:
        self.at = snapshot_index(self.snaps, a.snap)
        yield Step(self.runner.changes(self.at))

    def step(self, a) -> Steps:
        self.at += 1
        yield Step(self.runner.changes(self.at))
