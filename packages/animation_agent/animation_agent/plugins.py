"""
Manim plugins the generated scenes may use, and the prompt section ("cards") that teaches them.

Each plugin opens its whole public API, minus a short ban list (3D objects,
scene classes, file/network access, things that crash). The card lists
every allowed class with its real constructor arguments and the plugin's
own public methods, generated from the installed code so it can't drift,
plus one example scene that has been rendered through the real pipeline
(examples/plugins/) and the rules learned while testing it.

manim_codegen._static_check uses `allowed_imports()` to reject any import
of a plugin name the card doesn't offer.
"""

from __future__ import annotations

import importlib
import inspect
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent / "examples" / "plugins"
MAX_SIGNATURE_CHARS = 160


@dataclass(frozen=True)
class Plugin:
    module: str
    title: str
    use_for: str
    example: str  # file in examples/plugins/
    rules: str
    exclude: frozenset[str] = frozenset()
    list_methods: bool = True  # False where the plugin's methods are its own internals


PLUGINS: tuple[Plugin, ...] = (
    Plugin(
        module="manim_fa_physics",
        title="Fields, charges, optics and waves",
        use_for="magnets and magnetic fields, charges and electric fields, current in wires, lenses and light "
                "rays, standing waves, pendulums",
        example="fields.py",
        rules=(
            "- Keep a field's x_range within [-1.8, 1.8] and y_range within [-3.2, 3.2] (the narrow frame).\n"
            "- Draw the field first and the magnet/charges after it, so the field's arrows don't cover them.\n"
            "- A field doesn't follow its source. To show it change, build the field for the source's new "
            "position (on a .copy()) and Transform the old field into it while the source moves.\n"
            "- Labels on top of a field are allowed; give them a contrasting colour and keep them off the "
            "dense area right next to the poles or charges."
        ),
        # Space/SpaceScene replace GridLayoutScene; the waves are 3D surfaces.
        exclude=frozenset({"Space", "SpaceScene", "RadialWave", "LinearWave"}),
    ),
    Plugin(
        module="manim_chemistry",
        title="Chemistry",
        use_for="molecules and reactions (via `animation_agent.molecules`), chemical formulas, Bohr atoms, "
                "single atoms and bonds",
        example="molecules.py",
        rules=(
            "- Draw a molecule with `molecule(\"<PubChem name>\")` from `animation_agent.molecules`: coloured, "
            "labelled atoms joined by bonds. The name must be a string literal (it is fetched before the "
            "render). `molecule(name, hydrogens=False)` leaves out hydrogens on carbon.\n"
            "- `atoms(mol, \"Br\")` is a VGroup of that element's atoms; `bond(mol, \"C\", \"Br\")` is the bond "
            "between them. Use them to move, recolour or remove parts: a bond breaking, a group leaving.\n"
            "- A single atom or ion (bromide, Na+) has no bonds: draw it as a Circle with a MathTex symbol.\n"
            "- Charges and lone pairs are not drawn: add them with MathTex (e.g. MathTex(\"-\")) or Dot.\n"
            "- Mechanism arrows are CurvedArrow from the electron source to the atom it attacks.\n"
            "- Do not import GraphMolecule/MMoleculeObject or call molecule_from_pubchem/molecule_from_file: "
            "use molecule()."
        ),
        exclude=frozenset({
            # files, parsers and the network
            "ASNTParser", "FileHandler", "JSONParser", "MolParser", "SDFParser", "XMLParser",
            "PubchemAPIManager", "Element", "GenericElement",
            # 3D (OpenGL) objects
            "Orbital", "ThreeDAtom", "ThreeDBond", "ThreeDMolecule",
            # molecules come from animation_agent.molecules; these need raw structure data
            "GraphMolecule", "MMoleculeObject", "NamedMolecule", "GMAnimationBuilder", "BaseMBondObject",
            # needs a data file
            "PeriodicTable",
            # the building blocks molecule() assembles; too low-level to draw with by hand
            "MAtomObject", "SimpleBond", "DoubleBond", "TripleBond",
        }),
        list_methods=False,
    ),
    Plugin(
        module="manim_circuit",
        title="Circuits",
        use_for="circuit diagrams: sources, resistors, capacitors, inductors, op-amps, ground, wires",
        example="circuits.py",
        rules=(
            "- Build the components, shift them apart, add them to a Circuit with add_components(), and join "
            "terminals with circuit.add_wire(a, b). Terminals: two-terminal parts use "
            "get_terminals(\"left\"/\"right\"); sources use get_terminals(\"positive\"/\"negative\").\n"
            "- Place the whole Circuit once with place_in_area.\n"
            "- Built-in value labels (e.g. \"9 V\") are small. For a value the narration stresses, add your own "
            "MathTex (font_size >= 36) next to the component."
        ),
        exclude=frozenset({"Source", "Node"}),  # a base class and the wire bookkeeping
    ),
    Plugin(
        module="manim_dsa",
        title="Data structures",
        use_for="arrays, stacks, graphs, trees and variables, with highlighting, swapping, pushing and popping",
        example="data_structures.py",
        rules=(
            "- The i-th box of an MArray/MStack is `arr.elements[i]` (it has .square and .value). Do not "
            "index the array itself: `arr[0]` is a hidden helper object.\n"
            "- Animate the structure's own methods: `self.play(arr.animate.swap(i, j))`, "
            "`self.play(arr.elements[i].animate.highlight(YELLOW))`, `arr.animate.append(7)`.\n"
            "- MGraph/MTree take a dict of node -> neighbours; give MGraph nodes_position within about "
            "±1.5 wide and ±3 tall.\n"
            "- Colour themes: style=MArrayStyle.BLUE (or .PURPLE/.GREEN/.DEFAULT; likewise MStackStyle, "
            "MGraphStyle, MTreeStyle, MVariableStyle)."
        ),
    ),
)

# The helper module the chemistry card points at.
MOLECULE_MODULE = "animation_agent.molecules"
MOLECULE_HELPERS = frozenset({"molecule", "atoms", "bond"})

# Names generated code may never use, even as an attribute: they read files or the network,
# or bypass the molecule cache.
FORBIDDEN_PLUGIN_NAMES = frozenset({
    "molecule_from_pubchem", "molecule_from_file", "molecule_from_string", "PubchemAPIManager",
})


def _public_classes(plugin: Plugin) -> dict[str, type]:
    module = importlib.import_module(plugin.module)
    names = getattr(module, "__all__", None) or dir(module)
    found = {}
    for name in names:
        obj = getattr(module, name, None)
        if (inspect.isclass(obj) and not name.startswith("_") and name not in plugin.exclude
                and obj.__module__.startswith(plugin.module)):
            found[name] = obj
    return found


@cache
def allowed_imports() -> dict[str, frozenset[str]]:
    """Module -> the names generated code may import from it."""
    allowed = {p.module: frozenset(_public_classes(p)) for p in PLUGINS}
    allowed[MOLECULE_MODULE] = MOLECULE_HELPERS
    return allowed


def _default(value) -> str:
    if isinstance(value, float):
        return f"{value:.3g}"
    text = repr(value)
    text = re.sub(r"ManimColor\('(#[0-9A-Fa-f]+)'\)", r"'\1'", text)
    text = re.sub(r"array\(\[([^\]]*)\]\)", lambda m: "[" + re.sub(r"\s+", " ", m.group(1)).strip() + "]", text)
    if "object at 0x" in text or len(text) > 40:
        return "…"
    return text


def _signature(obj) -> str:
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        return "(…)"
    parts = []
    for p in sig.parameters.values():
        if p.name == "self":
            continue
        if p.kind is p.VAR_POSITIONAL:
            parts.append(f"*{p.name}")
        elif p.kind is p.VAR_KEYWORD:
            parts.append(f"**{p.name}")
        elif p.default is p.empty:
            parts.append(p.name)
        else:
            parts.append(f"{p.name}={_default(p.default)}")
    text = "(" + ", ".join(parts) + ")"
    return text if len(text) <= MAX_SIGNATURE_CHARS else text[: MAX_SIGNATURE_CHARS - 2] + "…)"


def _own_methods(cls: type, root: str) -> list[str]:
    """Public methods the plugin itself defines on `cls` (not ones inherited from manim)."""
    methods = {}
    for klass in reversed(cls.__mro__):
        if not getattr(klass, "__module__", "").startswith(root):
            continue
        for name, member in vars(klass).items():
            if name.startswith("_") or not inspect.isfunction(member):
                continue
            methods[name] = f".{name}{_signature(member)}"
    return list(methods.values())


def _class_listing(plugin: Plugin) -> str:
    lines = []
    for name, cls in _public_classes(plugin).items():
        lines.append(f"  {name}{_signature(cls)}")
        methods = _own_methods(cls, plugin.module) if plugin.list_methods else []
        if methods:
            lines.append("      methods: " + "  ".join(methods))
    return "\n".join(lines)


def _molecule_listing() -> str:
    from animation_agent import molecules

    return "\n".join(
        f"  {name}{_signature(getattr(molecules, name))}  — {inspect.getdoc(getattr(molecules, name)).splitlines()[0]}"
        for name in sorted(MOLECULE_HELPERS)
    )


def _card(plugin: Plugin) -> str:
    names = sorted(_public_classes(plugin))
    imports = f"from {plugin.module} import <names below>"
    listing = _class_listing(plugin)
    if plugin.module == "manim_chemistry":
        imports += f"\n  and: from {MOLECULE_MODULE} import {', '.join(sorted(MOLECULE_HELPERS))}"
        listing = _molecule_listing() + "\n" + listing
    example = (EXAMPLES_DIR / plugin.example).read_text().strip()
    return (
        f"### {plugin.title} — {plugin.module}\n"
        f"Use for: {plugin.use_for}.\n"
        f"Import: {imports}\n"
        f"Classes ({len(names)}):\n{listing}\n"
        f"Rules:\n{plugin.rules}\n"
        f"Example (rendered and checked):\n{example}"
    )


@cache
def plugin_cards() -> str:
    """The prompt section for every plugin."""
    return "\n\n".join(_card(p) for p in PLUGINS)


def plugin_cards_for(code: str) -> str:
    """The cards for just the plugins `code` imports ("" if none), for the repair prompts, which
    have no system prompt and so would otherwise fix plugin code without its API."""
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ""
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    if MOLECULE_MODULE in modules:
        modules.add("manim_chemistry")
    return "\n\n".join(_card(p) for p in PLUGINS if p.module in modules)


def plugin_names_used(code: str) -> list[str]:
    """`module.Name` for every plugin name `code` imports (for the render log)."""
    import ast

    used = []
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.ImportFrom) and node.module in allowed_imports():
            used += [f"{node.module}.{alias.name}" for alias in node.names]
    return used
