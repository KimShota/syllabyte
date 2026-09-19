from manim import *


class ExampleEquationAndPlot(Scene):
    """Example: an equation, then a small transform into an axes/plot
    (visual.kind == 'equation' or 'plot'). Uses MathTex (requires LaTeX)
    and a compact Axes scaled to the narrow frame."""

    def construct(self):
        eq = MathTex(r"f(n) = O(n^2)", color=WHITE)
        eq.scale_to_fit_width(min(eq.width, 3.5))
        self.play(Write(eq), run_time=1.2)
        self.wait(0.6)

        axes = Axes(
            x_range=[0, 5, 1], y_range=[0, 25, 5],
            x_length=3.4, y_length=3.4,
            axis_config={"include_tip": False, "font_size": 20},
        )
        graph = axes.plot(lambda x: x**2, color=BLUE, x_range=[0, 5])
        axes_group = VGroup(axes, graph)
        axes_group.scale_to_fit_width(min(axes_group.width, 3.9))

        self.play(Transform(eq, eq.copy().scale(0.6).to_edge(UP)), run_time=0.6)
        axes_group.next_to(eq, DOWN, buff=0.6)
        self.play(Create(axes), Create(graph), run_time=1.4)
        self.wait(1.0)
