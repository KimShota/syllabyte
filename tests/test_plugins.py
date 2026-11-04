"""Manim plugins in generated scenes (animation_agent/plugins.py, molecules.py). No LLM or network calls.

Set SYLLABYTE_RENDER_TESTS=1 to also render every plugin example through the real render path
(slow; needs PubChem once to fill the molecule cache)."""

import json
import os
from pathlib import Path

import numpy as np
import pytest
from manim import ArrowVectorField, Text

from animation_agent import molecules, plugins
from animation_agent.layout_audit import collect_units
from animation_agent.manim_codegen import UnsafeCodeError, check_beat_structure, validate_generated_code
from animation_agent.manim_prompt import _build_system_prompt, build_layout_repair_prompt, build_repair_prompt
from syllabyte_common.models import Beat, RenderResult, Segment, SlideRef

EXAMPLES = sorted(plugins.EXAMPLES_DIR.glob("*.py"))
HEADER = "from manim import *\nfrom animation_agent.layout import GridLayoutScene\n"


def scene(imports: str = "", body: str = "self.end_beat(1)") -> str:
    return f"{HEADER}{imports}\n\nclass Seg0(GridLayoutScene):\n    def construct(self):\n        self.setup_grid()\n        {body}\n"


class TestStaticCheck:
    def test_offered_plugin_names_pass(self):
        validate_generated_code(scene("from manim_fa_physics import BarMagnet, BarMagneticField"))
        validate_generated_code(scene("from manim_dsa import MArray\nfrom animation_agent.molecules import molecule, atoms"))

    @pytest.mark.parametrize("line, why", [
        ("from manim_chemistry import GraphMolecule", "not one of the plugin names offered"),
        ("from manim_fa_physics import SpaceScene", "not one of the plugin names offered"),
        ("from manim_chemistry import *", "one by one"),
        ("import manim_dsa", "forbidden import"),
        ("from manim_pymunk import SpaceScene", "forbidden import"),
        ("from animation_agent.molecules import fetch_molecule", "not one of the plugin names offered"),
    ])
    def test_anything_else_from_a_plugin_is_rejected(self, line, why):
        with pytest.raises(UnsafeCodeError, match=why):
            validate_generated_code(scene(line))

    def test_the_network_and_file_loaders_are_rejected_even_as_attributes(self):
        with pytest.raises(UnsafeCodeError, match="molecule_from_pubchem"):
            validate_generated_code(scene("from manim_chemistry import BohrAtom", "x = BohrAtom.molecule_from_pubchem(name='x')"))

    def test_the_old_rules_still_hold(self):
        with pytest.raises(UnsafeCodeError):
            validate_generated_code(scene("import os"))


class TestCards:
    def test_every_offered_name_is_listed_in_the_prompt(self):
        prompt = _build_system_prompt("Seg0")
        for module, names in plugins.allowed_imports().items():
            for name in names:
                assert f"  {name}(" in prompt, f"{module}.{name}"

    def test_banned_classes_are_neither_offered_nor_listed(self):
        offered = plugins.allowed_imports()
        assert {"SpaceScene", "Space", "RadialWave"}.isdisjoint(offered["manim_fa_physics"])
        assert {"GraphMolecule", "PubchemAPIManager", "ThreeDMolecule", "FileHandler"}.isdisjoint(offered["manim_chemistry"])

    def test_the_prompt_no_longer_forbids_every_plugin(self):
        prompt = _build_system_prompt("Seg0")
        assert "any Manim plugin or plugin name not listed under Plugins" in prompt
        assert "Plugins: when a beat's visual names" in prompt and "keep their own colours" in prompt

    @pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
    def test_each_example_is_in_its_card_and_passes_the_checks(self, example):
        code = example.read_text()
        assert code.strip() in plugins.plugin_cards()
        validate_generated_code(code)
        n_beats = code.count("self.end_beat(")
        assert check_beat_structure(code, n_beats) is None

    def test_repairs_get_the_cards_of_the_plugins_the_code_uses_only(self):
        seg = Segment(phase="deliver", source_refs=[SlideRef(deck_name="d", slide_number=1)],
                      beats=[Beat(narration="n", visual="v")])
        with_plugin = scene("from manim_dsa import MArray")
        for prompt in (build_repair_prompt(with_plugin, "err", seg, [2.0], "Seg0"),
                       build_layout_repair_prompt(with_plugin, "p", seg, [2.0], "Seg0")):
            assert "### Data structures" in prompt and "### Chemistry" not in prompt
        assert "###" not in build_repair_prompt(scene(), "err", seg, [2.0], "Seg0")
        molecule_code = scene("from animation_agent.molecules import molecule")
        assert "### Chemistry" in build_repair_prompt(molecule_code, "err", seg, [2.0], "Seg0")

    def test_plugin_names_used(self):
        code = scene("from manim_dsa import MArray, MGraph\nfrom animation_agent.molecules import molecule")
        assert plugins.plugin_names_used(code) == [
            "manim_dsa.MArray", "manim_dsa.MGraph", "animation_agent.molecules.molecule",
        ]

    def test_old_render_results_load_without_plugin_fields(self):
        r = RenderResult.model_validate({"segment_index": 0, "tier": "llm_first_try", "attempts": 1, "render_seconds": 1.0})
        assert r.plugins_used == [] and r.plugins_tried == []


def pubchem_record(elements: list[int], bonds: list[tuple[int, int]] | None) -> dict:
    n = len(elements)
    compound = {"atoms": {"aid": list(range(1, n + 1)), "element": elements},
                "coords": [{"type": [1], "aid": list(range(1, n + 1)),
                            "conformers": [{"x": [float(i) for i in range(n)], "y": [0.0] * n}]}]}
    if bonds:
        compound["bonds"] = {"aid1": [a for a, _ in bonds], "aid2": [b for _, b in bonds], "order": [1] * len(bonds)}
    return {"PC_Compounds": [compound]}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SYLLABYTE_MOLECULE_DIR", str(tmp_path))

    def put(name: str, record: dict) -> None:
        (tmp_path / f"{name}.json").write_text(json.dumps(record))

    def no_network(*a, **k):
        raise AssertionError("tried the network")

    monkeypatch.setattr(molecules.urllib.request, "urlopen", no_network)
    return put


class TestMolecules:
    def test_names_are_found_only_as_literals(self):
        code = 'a = molecule("ethanol")\nb = molecule("ethanol", hydrogens=False)\nc = molecule("water")'
        assert molecules.molecule_names(code) == ["ethanol", "water"]
        assert "string literal" in molecules.prefetch_molecules("n = 'x'\nm = molecule(n)")

    def test_a_cached_molecule_is_not_fetched_again(self, cache):
        cache("hydrogen-bromide", pubchem_record([35, 1], [(1, 2)]))
        assert molecules.prefetch_molecules('m = molecule("Hydrogen bromide")') is None

    def test_a_single_atom_is_reported_with_what_to_draw_instead(self, cache):
        cache("bromide", pubchem_record([35], None))
        problem = molecules.prefetch_molecules('m = molecule("bromide")')
        assert "single atom or ion" in problem and "Circle" in problem

    def test_atoms_and_bonds_are_found_by_element(self, cache):
        cache("bromomethane", pubchem_record([35, 6, 1, 1, 1], [(1, 2), (2, 3), (2, 4), (2, 5)]))
        mol = molecules.molecule("bromomethane")
        assert len(molecules.atoms(mol, "H")) == 3 and len(molecules.atoms(mol, "Br")) == 1
        assert molecules.bond(mol, "Br", "C") is mol.edges[(1, 2)]
        with pytest.raises(ValueError, match="no O-H bond"):
            molecules.bond(mol, "O", "H")

    def test_dark_atoms_are_brightened_for_the_black_background(self, cache):
        cache("bromomethane", pubchem_record([35, 6, 1, 1, 1], [(1, 2), (2, 3), (2, 4), (2, 5)]))
        from animation_agent.layout_audit import contrast_ratio

        bromine = molecules.atoms(molecules.molecule("bromomethane"), "Br")[0]
        rgb = np.array(bromine.get_fill_color().to_rgb())
        assert contrast_ratio(rgb, np.zeros(3)) >= molecules.MIN_ATOM_CONTRAST


def test_a_vector_field_is_background_to_the_layout_audit():
    field = ArrowVectorField(lambda p: np.array([1.0, 0.0, 0.0]), x_range=[-1, 1, 0.5], y_range=[-1, 1, 0.5])
    label = Text("B", font_size=36)
    units = collect_units([field, label], {})
    assert [u.mob for u in units] == [label]


@pytest.mark.skipif(not os.environ.get("SYLLABYTE_RENDER_TESTS"), reason="set SYLLABYTE_RENDER_TESTS=1 to render")
@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_each_example_renders_cleanly(example, tmp_path):
    from animation_agent.layout import BEATS_FILE
    from animation_agent.renderer import _try_render

    code = example.read_text()
    n_beats = code.count("self.end_beat(")
    durations = [3.0] * n_beats
    (tmp_path / BEATS_FILE).write_text(json.dumps(durations))
    class_name = next(line.split()[1].split("(")[0] for line in code.splitlines() if line.startswith("class "))
    ok, error, _, layout = _try_render(Path(tmp_path), code, class_name, "low", n_beats, sum(durations))
    assert ok, error
    assert layout.findings == []
