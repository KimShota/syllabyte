from manim import *

from animation_agent.layout import GridLayoutScene


class ExampleBulletReveal(GridLayoutScene):
    """Example: a title + up to 3 bullets, revealed one at a time
    (visual.kind == 'bullets'). Grid placement keeps every element inside a
    fixed anchor so the Critic can reason about (and fix) layout by cell."""

    def construct(self):
        self.setup_grid()
        title = Text("Complexity Classes", font_size=44, color=YELLOW)
        self.place_at_grid(title, "A3", scale_factor=0.9)
        self.play(FadeIn(title), run_time=0.6)

        bullets = VGroup(
            Text("O(1) — constant", font_size=36, color=WHITE),
            Text("O(n) — linear", font_size=36, color=WHITE),
            Text("O(n^2) — quadratic", font_size=36, color=WHITE),
        ).arrange(DOWN, buff=0.5)
        self.place_in_area(bullets, "C2", "E5", scale_factor=0.9)

        for bullet in bullets:
            self.play(Write(bullet), run_time=0.7)
            self.wait(0.4)

        self.wait(0.8)
        self.play(FadeOut(title), FadeOut(bullets), run_time=0.5)
