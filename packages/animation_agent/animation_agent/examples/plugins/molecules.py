from manim import *

from animation_agent.layout import GridLayoutScene
from animation_agent.molecules import atoms, bond, molecule


class ExampleSubstitution(GridLayoutScene):
    """Hydroxide attacks the carbon of bromomethane; the C-Br bond breaks and bromine leaves."""

    def construct(self):
        self.setup_grid()

        # === Beat 1 ===
        substrate = molecule("bromomethane")
        self.place_in_area(substrate, "B2", "C5", scale_factor=0.8)
        hydroxide = molecule("hydroxide")
        self.place_in_area(hydroxide, "E2", "E3", scale_factor=0.8)
        charge = MathTex("-", color=YELLOW, font_size=48).next_to(hydroxide, UR, buff=0.05)
        self.play(FadeIn(substrate), FadeIn(hydroxide), Write(charge), run_time=1.5)
        self.end_beat(1)

        # === Beat 2 ===
        carbon = atoms(substrate, "C")[0]
        attack = CurvedArrow(atoms(hydroxide, "O")[0].get_top(), carbon.get_bottom(), color=YELLOW)
        self.play(Create(attack), Indicate(carbon), run_time=1.5)
        self.end_beat(2)

        # === Beat 3 ===
        bromine = atoms(substrate, "Br")[0]
        self.play(FadeOut(bond(substrate, "C", "Br")), bromine.animate.shift(LEFT * 0.8), run_time=1.5)
        self.end_beat(3)
