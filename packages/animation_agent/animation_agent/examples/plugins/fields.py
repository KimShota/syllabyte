from manim import *
from manim_fa_physics import BarMagnet, BarMagneticField

from animation_agent.layout import GridLayoutScene


class ExampleMagnetField(GridLayoutScene):
    """A bar magnet's field, then the magnet moving toward a loop with its field following it."""

    def construct(self):
        self.setup_grid()

        # === Beat 1 ===
        magnet = BarMagnet(north=UP * 0.8, south=DOWN * 0.8, height=1.6, width=0.6)
        self.place_at_grid(magnet, "C3", scale_factor=1.0)
        field = BarMagneticField(magnet, x_range=[-1.8, 1.8, 0.45], y_range=[-3.2, 3.2, 0.45])
        self.play(Create(field), run_time=1.2)
        self.play(FadeIn(magnet), run_time=0.6)
        self.end_beat(1)

        # === Beat 2 ===
        loop = Circle(radius=0.55, color=YELLOW).stretch(0.35, 1)
        self.place_at_grid(loop, "F3", scale_factor=1.0)
        self.play(Create(loop), run_time=0.8)
        moved = magnet.copy().shift(DOWN * 1.6)
        new_field = BarMagneticField(moved, x_range=[-1.8, 1.8, 0.45], y_range=[-3.2, 3.2, 0.45])
        self.play(magnet.animate.shift(DOWN * 1.6), Transform(field, new_field), run_time=1.5)
        self.end_beat(2)
