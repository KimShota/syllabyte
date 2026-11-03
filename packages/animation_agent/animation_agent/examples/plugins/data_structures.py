from manim import *
from manim_dsa import MArray, MGraph

from animation_agent.layout import GridLayoutScene


class ExampleArrayAndGraph(GridLayoutScene):
    """An array, two elements highlighted and swapped, then a small directed graph."""

    def construct(self):
        self.setup_grid()

        # === Beat 1 ===
        array = MArray([5, 2, 8, 1])
        self.place_in_area(array, "A1", "B6", scale_factor=0.8)
        self.play(Create(array), run_time=1.5)
        self.end_beat(1)

        # === Beat 2 ===
        self.play(array.elements[1].animate.highlight(YELLOW), array.elements[3].animate.highlight(YELLOW), run_time=0.8)
        self.play(array.animate.swap(1, 3), run_time=1.0)
        self.end_beat(2)

        # === Beat 3 ===
        graph = MGraph(
            {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []},
            nodes_position={"A": UP * 1.2, "B": LEFT, "C": RIGHT, "D": DOWN * 1.2},
        )
        self.place_in_area(graph, "C2", "F5", scale_factor=1.0)
        self.play(Create(graph), run_time=2.0)
        self.end_beat(3)
