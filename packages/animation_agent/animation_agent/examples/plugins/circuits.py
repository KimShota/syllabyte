from manim import *
from manim_circuit import Circuit, Resistor, VoltageSource

from animation_agent.layout import GridLayoutScene


class ExampleSeriesCircuit(GridLayoutScene):
    """A 9 V source driving a 3 ohm resistor, then the current arrow."""

    def construct(self):
        self.setup_grid()

        # === Beat 1 ===
        source = VoltageSource(value=9, direction=LEFT).shift(LEFT * 1.2)
        load = Resistor(label=3, direction=RIGHT).rotate(PI / 2).shift(RIGHT * 1.2)
        circuit = Circuit()
        circuit.add_components(source, load)
        circuit.add_wire(source.get_terminals("positive"), load.get_terminals("right"))
        circuit.add_wire(source.get_terminals("negative"), load.get_terminals("left"))
        self.place_in_area(circuit, "B1", "D6", scale_factor=1.0)
        self.play(Create(circuit), run_time=2.0)
        self.end_beat(1)

        # === Beat 2 ===
        current = Arrow(LEFT * 0.7, RIGHT * 0.7, color=YELLOW, buff=0).next_to(circuit, UP, buff=0.15)
        label = MathTex("I", color=YELLOW, font_size=44).next_to(current, UP, buff=0.1)
        self.play(GrowArrow(current), Write(label), run_time=1.5)
        self.end_beat(2)
