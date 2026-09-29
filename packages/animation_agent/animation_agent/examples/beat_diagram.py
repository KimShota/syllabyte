from manim import *

from animation_agent.layout import GridLayoutScene


class ExampleBeatDiagram(GridLayoutScene):
    """Example: one evolving, visual-first diagram (a stack), one code block
    per beat, each ending in self.end_beat(N). Beats:
      1. "A stack is like a pile of plates."      -> an empty open-top container
      2. "Each push drops a new item on top."     -> three boxes drop in, one at a time
      3. "A pop can only take the top item off."  -> the top box flashes and lifts out
      4. "Last in, first out."                    -> ring the lifted box, label 'LIFO'
    The idea is carried by motion; the only text is one short label. The
    whole diagram is composed first and grid-placed once, then revealed and
    changed part by part across beats."""

    def construct(self):
        self.setup_grid()

        container = VGroup(
            Line(LEFT * 0.9 + UP * 1.4, LEFT * 0.9 + DOWN * 1.4),
            Line(LEFT * 0.9 + DOWN * 1.4, RIGHT * 0.9 + DOWN * 1.4),
            Line(RIGHT * 0.9 + DOWN * 1.4, RIGHT * 0.9 + UP * 1.4),
        ).set_stroke(WHITE, 4)
        boxes = VGroup(*[
            RoundedRectangle(width=1.4, height=0.55, corner_radius=0.1, color=c, fill_opacity=0.7)
            for c in (BLUE, GREEN, ORANGE)
        ]).arrange(UP, buff=0.08)
        boxes.next_to(container[1], UP, buff=0.08)
        stack = VGroup(container, boxes)
        self.place_in_area(stack, "B2", "F5", scale_factor=1.0)

        # === Beat 1 ===
        self.play(Create(container), run_time=1.2)
        self.end_beat(1)

        # === Beat 2 ===
        for box in boxes:
            self.play(FadeIn(box, shift=DOWN * 2), run_time=0.7)
        self.end_beat(2)

        # === Beat 3 ===
        top = boxes[-1]
        self.play(Indicate(top, color=YELLOW), run_time=0.8)
        self.play(top.animate.shift(UP * 2.2), run_time=1.0)
        self.end_beat(3)

        # === Beat 4 ===
        label = Text("LIFO", font_size=40, color=YELLOW)
        self.place_in_area(label, "A3", "A4", scale_factor=0.9)
        self.play(Circumscribe(top, color=YELLOW), FadeIn(label), run_time=1.2)
        self.end_beat(4)
