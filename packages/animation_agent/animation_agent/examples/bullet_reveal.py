from manim import *


class ExampleBulletReveal(Scene):
    """Example: a title + up to 3 bullets, revealed one at a time
    (visual.kind == 'bullets'). Stacks vertically — this is a narrow
    9:16 frame, not a wide slide."""

    def construct(self):
        title = Text("Complexity Classes", font_size=44, color=YELLOW)
        title.scale_to_fit_width(min(title.width, 3.9))
        title.to_edge(UP)
        self.play(FadeIn(title), run_time=0.6)

        bullets = VGroup(
            Text("O(1) — constant", font_size=36, color=WHITE),
            Text("O(n) — linear", font_size=36, color=WHITE),
            Text("O(n^2) — quadratic", font_size=36, color=WHITE),
        ).arrange(DOWN, buff=0.5)
        bullets.scale_to_fit_width(min(bullets.width, 3.9))
        bullets.next_to(title, DOWN, buff=0.7)

        for bullet in bullets:
            self.play(Write(bullet), run_time=0.7)
            self.wait(0.4)

        self.wait(0.8)
        self.play(FadeOut(title), FadeOut(bullets), run_time=0.5)
