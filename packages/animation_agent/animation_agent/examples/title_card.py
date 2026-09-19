from manim import *


class ExampleTitleCard(Scene):
    """Example: a simple title/hook card (visual.kind == 'title')."""

    def construct(self):
        title = Text("What is Big-O Notation?", font_size=48, color=YELLOW)
        title.scale_to_fit_width(min(title.width, 3.9))
        self.play(FadeIn(title), run_time=0.8)
        self.wait(2.2)
        self.play(FadeOut(title), run_time=0.5)
