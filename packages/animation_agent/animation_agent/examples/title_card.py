from manim import *

from animation_agent.layout import GridLayoutScene


class ExampleTitleCard(GridLayoutScene):
    """Example: a simple title/hook card."""

    def construct(self):
        self.setup_grid()
        title = Text("What is Big-O Notation?", font_size=48, color=YELLOW)
        self.place_in_area(title, "C1", "D6", scale_factor=0.9)
        self.play(FadeIn(title), run_time=0.8)
        self.wait(2.2)
        self.play(FadeOut(title), run_time=0.5)
