from manim import *

from animation_agent.layout import GridLayoutScene


class ExampleEquationAndPlot(GridLayoutScene):
    """Example: an equation, then a small transform into an axes/plot. Uses
    MathTex (requires LaTeX) and a compact Axes scaled to the narrow frame."""

    def construct(self):
        self.setup_grid()
        eq = MathTex(r"f(n) = O(n^2)", color=WHITE)
        self.place_at_grid(eq, "A3", scale_factor=0.9)
        self.play(Write(eq), run_time=1.2)
        self.wait(0.6)

        axes = Axes(
            x_range=[0, 5, 1], y_range=[0, 25, 5],
            x_length=3.4, y_length=3.4,
            axis_config={"include_tip": False, "font_size": 20},
        )
        graph = axes.plot(lambda x: x**2, color=BLUE, x_range=[0, 5])
        axes_group = VGroup(axes, graph)
        self.place_in_area(axes_group, "C2", "E5", scale_factor=0.9)

        self.play(Transform(eq, eq.copy().scale(0.6).move_to(self.grid["A3"])), run_time=0.6)
        self.play(Create(axes), Create(graph), run_time=1.4)
        self.wait(1.0)
