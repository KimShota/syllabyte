from manim import *

from animation_agent.layout import GridLayoutScene


class ExampleEquationAndPlot(GridLayoutScene):
    """Example: an equation, then a plot that makes it visible. Uses MathTex
    (requires LaTeX) and a compact Axes scaled to the narrow frame. Beats:
      1. "Quadratic growth is written f of n equals O of n squared."  -> write the formula
      2. "Plot it, and the curve bends upward faster and faster."      -> formula shrinks up, curve draws
      3. "Doubling n from two to four quadruples the work."           -> dots at n=2 and n=4, drop lines, flash"""

    def construct(self):
        self.setup_grid()

        # === Beat 1 ===
        eq = MathTex(r"f(n) = O(n^2)", color=WHITE)
        self.place_in_area(eq, "C2", "C5", scale_factor=0.9)
        self.play(Write(eq), run_time=1.4)
        self.end_beat(1)

        # === Beat 2 ===
        axes = Axes(
            x_range=[0, 5, 1], y_range=[0, 25, 5],
            x_length=3.4, y_length=3.4,
            axis_config={"include_tip": False, "font_size": 20},
        )
        graph = axes.plot(lambda x: x**2, color=BLUE, x_range=[0, 5])
        axes_group = VGroup(axes, graph)
        self.place_in_area(axes_group, "C2", "F5", scale_factor=0.9)
        self.play(eq.animate.scale(0.6).move_to(self.grid["A3"] + RIGHT * 0.33), run_time=0.6)
        self.play(Create(axes), run_time=0.8)
        self.play(Create(graph), run_time=1.2)
        self.end_beat(2)

        # === Beat 3 ===
        dot2 = Dot(axes.c2p(2, 4), color=YELLOW)
        dot4 = Dot(axes.c2p(4, 16), color=ORANGE)
        drop2 = DashedLine(axes.c2p(2, 0), axes.c2p(2, 4), color=YELLOW)
        drop4 = DashedLine(axes.c2p(4, 0), axes.c2p(4, 16), color=ORANGE)
        self.play(GrowFromCenter(dot2), Create(drop2), run_time=0.7)
        self.play(GrowFromCenter(dot4), Create(drop4), run_time=0.7)
        self.play(Flash(dot4, color=ORANGE), run_time=0.6)
        self.end_beat(3)
