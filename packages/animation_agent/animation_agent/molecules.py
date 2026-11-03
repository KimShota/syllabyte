"""
Molecules for generated scenes, without network access during a render.

A scene draws a molecule with `molecule("bromomethane")`: coloured atoms
(CPK colours, labelled with their symbols) joined by bonds, from
manim-chemistry's GraphMolecule. `atoms(mol, "H")` and `bond(mol, "C", "Br")`
pick out parts of it to move, recolour or remove (a bond breaking, a
leaving group).

The structure comes from a local cache, never the network: before each
render, renderer.py calls `prefetch_molecules(code)`, which finds the
molecule("...") calls (the name must be a string literal) and fetches each
missing one once from PubChem. A single atom or ion (bromide, Na+) has no
bonds, which GraphMolecule can't draw; the prefetch reports that so the
scene draws it as a labelled circle instead.

(manim-chemistry's other style, MMoleculeObject, is not offered: with
hydrogens drawn it fails inside the plugin with an UnboundLocalError.)
"""

from __future__ import annotations

import ast
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PUBCHEM_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{}/json"
FETCH_TIMEOUT_SECONDS = 30
HELPER = "molecule"

# Atomic number -> symbol, through xenon (PubChem records give atomic numbers).
_SYMBOLS = (
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn "
    "Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe"
).split()


class MoleculeNotFound(Exception):
    pass


def molecule_dir() -> Path:
    return Path(os.environ.get("SYLLABYTE_MOLECULE_DIR") or Path.home() / ".cache" / "syllabyte" / "molecules")


def _cache_path(name: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return molecule_dir() / f"{slug}.json"


def _compound(record: dict) -> dict:
    return record["PC_Compounds"][0]


def fetch_molecule(name: str) -> Path:
    """The cached PubChem record for `name`, fetched first if it isn't cached."""
    path = _cache_path(name)
    if path.exists():
        return path
    url = PUBCHEM_URL.format(urllib.parse.quote(name.strip()))
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
            record = json.loads(response.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise MoleculeNotFound(
                f'PubChem has no compound named "{name}". Use its common or IUPAC name '
                '(e.g. "bromomethane", "hydroxide", "ethanol").'
            ) from e
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record))
    tmp.replace(path)
    return path


def _literal_name(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None


def _helper_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == HELPER
    ]


def molecule_names(code: str) -> list[str]:
    """Names passed as a string literal to molecule() in `code`."""
    names = [name for call in _helper_calls(ast.parse(code)) if (name := _literal_name(call))]
    return list(dict.fromkeys(names))


def prefetch_molecules(code: str) -> str | None:
    """Caches every molecule `code` draws. Returns a problem for the repair
    prompt (an unknown name, a single atom, a name that isn't a literal),
    else None."""
    for call in _helper_calls(ast.parse(code)):
        if _literal_name(call) is None:
            return f'line {call.lineno}: molecule() needs the molecule\'s name as a string literal, e.g. molecule("ethanol").'
    for name in molecule_names(code):
        try:
            record = json.loads(fetch_molecule(name).read_text())
        except MoleculeNotFound as e:
            return str(e)
        except (urllib.error.URLError, OSError, ValueError) as e:  # offline, timeout, bad reply
            return f'Could not fetch "{name}" from PubChem ({e}). Draw it without molecule() this time.'
        if "bonds" not in _compound(record):
            return (
                f'"{name}" is a single atom or ion, which molecule() can\'t draw (it has no bonds). '
                'Draw it as a Circle with its symbol inside, e.g. VGroup(Circle(radius=0.3, color=RED), '
                'MathTex(r"Br^-")), and keep molecule() for things with bonds.'
            )
    return None


def _load(name: str) -> dict:
    path = _cache_path(name)
    if not path.exists():
        raise MoleculeNotFound(f'molecule "{name}" was not fetched before the render; pass its name as a string literal.')
    return json.loads(path.read_text())


def molecule(name: str, *, hydrogens: bool = True):
    """`name` (a PubChem name) as coloured, labelled atoms joined by bonds.
    hydrogens=False leaves out the hydrogens bonded to carbon."""
    from manim_chemistry import GraphMolecule

    record = _load(name)
    mol = GraphMolecule.molecule_from_string(
        json.dumps(record), format="json", ignore_hydrogens=not hydrogens, label=True,
    )
    atoms_data = _compound(record)["atoms"]
    mol.syllabyte_elements = {
        aid: _SYMBOLS[z - 1] if 0 < z <= len(_SYMBOLS) else "?"
        for aid, z in zip(atoms_data["aid"], atoms_data["element"])
    }
    _brighten_dark_atoms(mol)
    return mol


# Some CPK colours (Br, I, Fe, ...) are too dark on the black background for the layout audit's 3:1.
MIN_ATOM_CONTRAST = 3.5


def _brighten_dark_atoms(mol) -> None:
    import numpy as np
    from manim import BLACK, WHITE, interpolate_color

    from animation_agent.layout_audit import contrast_ratio

    def contrast(colour) -> float:
        return contrast_ratio(np.array(colour.to_rgb()), np.array(BLACK.to_rgb()))

    for dot in mol.atoms.values():
        original = dot.get_fill_color()
        if contrast(original) >= MIN_ATOM_CONTRAST:
            continue
        colour = next(
            (c for t in (0.2, 0.35, 0.5, 0.65, 0.8)
             if contrast(c := interpolate_color(original, WHITE, t)) >= MIN_ATOM_CONTRAST),
            WHITE,
        )
        dot.set_fill(colour, family=False)  # the atom only; its symbol keeps its colour


def atoms(mol, symbol: str):
    """A VGroup of `mol`'s atoms of element `symbol` (e.g. "H"), in PubChem order."""
    from manim import VGroup

    return VGroup(*(dot for aid, dot in mol.atoms.items() if mol.syllabyte_elements.get(aid) == symbol))


def bond(mol, a: str, b: str):
    """The first bond in `mol` between an atom of element `a` and one of element `b`."""
    for (u, v), line in mol.edges.items():
        if {mol.syllabyte_elements.get(u), mol.syllabyte_elements.get(v)} == {a, b}:
            return line
    raise ValueError(f"this molecule has no {a}-{b} bond")
