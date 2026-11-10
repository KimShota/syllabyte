"""Bounded numerical geometry for teaching diagrams. No Manim or model calls."""
from __future__ import annotations

import ast
import math
from functools import lru_cache
from itertools import product

import numpy as np


class FormulaXY:
    """Small, bounded arithmetic language; no attribute access, indexing, or Python execution."""
    functions = {"sin": np.sin, "cos": np.cos, "tan": np.tan, "exp": np.exp,
                 "log": np.log, "ln": np.log, "sqrt": np.sqrt, "abs": np.abs}

    def __init__(self, source: str):
        if not source.strip() or len(source) > 96:
            raise ValueError("formula must have 1-96 characters")
        try:
            self.tree = ast.parse(source.replace("^", "**"), mode="eval").body
        except (SyntaxError, RecursionError) as e:
            raise ValueError("use a formula in x and y with explicit products (*)") from e
        nodes = list(ast.walk(self.tree))
        if len(nodes) > 64:
            raise ValueError("formula is too complex; use at most 64 expression nodes")
        allowed = (ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Call, ast.Load,
                   ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd)
        for n in nodes:
            if not isinstance(n, allowed):
                raise ValueError("only arithmetic, x, y, pi, e, and supported functions are allowed")
            if isinstance(n, ast.Constant) and (type(n.value) not in (float, int) or not math.isfinite(float(n.value)) or abs(n.value) > 1e6):
                raise ValueError("constants must be finite numbers of magnitude at most 1000000")
            if isinstance(n, ast.Name) and n.id not in {"x", "y", "pi", "e", *self.functions}:
                raise ValueError(f"unsupported formula name: {n.id}")
            if isinstance(n, ast.Call) and (not isinstance(n.func, ast.Name) or n.func.id not in self.functions or len(n.args) != 1 or n.keywords):
                raise ValueError("supported functions take exactly one argument")
        def zero_factors(n):
            # A squared denominator can cross a pole without changing sign.
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow):
                return [n, *zero_factors(n.left)]
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult):
                return [n, *zero_factors(n.left), *zero_factors(n.right)]
            return [n]
        self.guards = [g for n in nodes if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)
                       for g in zero_factors(n.right)]
        self.guards += [g for n in nodes if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow)
                        and not (isinstance(n.right, ast.Constant) and n.right.value >= 0)
                        for g in zero_factors(n.left)]
        self.tans = [n.args[0] for n in nodes if isinstance(n, ast.Call) and n.func.id == "tan"]
        # Validate that function names aren't used as standalone numbers.
        self(0.5, 0.5)

    def _eval(self, n, x, y):
        if isinstance(n, ast.Constant):
            return np.float64(n.value)
        if isinstance(n, ast.Name):
            if n.id not in {"x", "y", "pi", "e"}:
                raise ValueError("a function name needs an argument")
            return {"x": x, "y": y, "pi": np.pi, "e": np.e}[n.id]
        if isinstance(n, ast.UnaryOp):
            v = self._eval(n.operand, x, y)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.Call):
            return self.functions[n.func.id](self._eval(n.args[0], x, y))
        a, b = self._eval(n.left, x, y), self._eval(n.right, x, y)
        return {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply,
                ast.Div: np.divide, ast.Pow: np.power}[type(n.op)](a, b)

    def __call__(self, x, y):
        with np.errstate(all="ignore"):
            return self._eval(self.tree, np.asarray(x, dtype=float), np.asarray(y, dtype=float))

    def continuous_between(self, start, end):
        """Conservative domain probes; never join across detected poles/undefined samples."""
        p = np.linspace(start, end, 9)
        with np.errstate(all="ignore"):
            if not np.all(np.isfinite(self(p[:, 0], p[:, 1]))):
                return False
            guards = [self._eval(n, p[:, 0], p[:, 1]) for n in self.guards]
            guards += [np.cos(self._eval(n, p[:, 0], p[:, 1])) for n in self.tans]
        return all(np.all(np.isfinite(g)) and not np.any(np.abs(g) < 1e-12)
                   and (np.all(np.asarray(g) > 0) or np.all(np.asarray(g) < 0)) for g in guards)


@lru_cache(maxsize=128)
def formula_xy(source: str) -> FormulaXY:
    return FormulaXY(source)


def slope_samples(source, xr, yr, density):
    f = formula_xy(source)
    out = []
    for x in np.linspace(*xr, density):
        for y in np.linspace(*yr, density):
            m = float(f(x, y))
            if np.isfinite(m):
                out.append((float(x), float(y), m))
    return out


def solution_curve(source, initial, xr, yr):
    """Adaptive RK4 with step doubling, both directions; finite budget and domain/box stops."""
    f = formula_xy(source)
    x0, y0 = initial
    if not xr[0] <= x0 <= xr[1] or not yr[0] <= y0 <= yr[1] or not np.isfinite(f(x0, y0)):
        raise ValueError("initial condition must be inside the axes where the slope is defined")
    span, height = xr[1] - xr[0], yr[1] - yr[0]

    def rk(x, y, h):
        k1 = float(f(x, y))
        k2 = float(f(x + h / 2, y + h * k1 / 2))
        k3 = float(f(x + h / 2, y + h * k2 / 2))
        k4 = float(f(x + h, y + h * k3))
        return y + h * (k1 + 2 * k2 + 2 * k3 + k4) / 6

    def walk(direction):
        x, y, h = float(x0), float(y0), direction * span / 100
        points = [(x, y)]
        boundary = xr[1] if direction > 0 else xr[0]
        for _ in range(2400):
            if abs(boundary - x) < span * 1e-10:
                break
            h = direction * min(abs(h), abs(boundary - x), span / 60)
            whole = rk(x, y, h)
            half = rk(x + h / 2, rk(x, y, h / 2), h / 2)
            good = (np.isfinite(half) and np.isfinite(whole) and yr[0] <= half <= yr[1]
                    and abs(half - whole) <= height * 1e-7
                    and abs(half - y) <= height / 30
                    and f.continuous_between((x, y), (x + h, half)))
            if not good:
                h /= 2
                if abs(h) < span * 1e-7:
                    break
                continue
            x, y = x + h, half
            points.append((x, y))
            h *= 1.5
        return points

    left, right = walk(-1), walk(1)
    return list(reversed(left))[:-1] + right


def line_intersections(first, second):
    """All intersections of line/segment/circle dictionaries, in lexicographic order."""
    def line_circle(line, circle):
        p, q, c = (np.array(v, float) for v in (line["p"], line["q"], circle["center"]))
        d, v, r = q - p, p - c, circle["radius"]
        aa, bb, cc = d @ d, 2 * (v @ d), v @ v - r * r
        disc = bb * bb - 4 * aa * cc
        tol = 1e-10 * max(1, bb * bb, abs(4 * aa * cc))
        if disc < -tol:
            return []
        ts = [-bb / (2 * aa)] if abs(disc) <= tol else [(-bb - np.sqrt(disc)) / (2 * aa), (-bb + np.sqrt(disc)) / (2 * aa)]
        return [p + t * d for t in ts if line["kind"] != "segment" or -1e-9 <= t <= 1 + 1e-9]

    a, b = first, second
    if a["kind"] != "circle" and b["kind"] != "circle":
        p, q, r, s = (np.array(v, float) for v in (a["p"], a["q"], b["p"], b["q"]))
        u, v = q - p, s - r
        cross = lambda x, y: x[0] * y[1] - x[1] * y[0]
        det = cross(u, v)
        if abs(det) < 1e-10 * np.linalg.norm(u) * np.linalg.norm(v):
            if abs(cross(r - p, u)) < 1e-9 * np.linalg.norm(u):
                # Collinear segments may be disjoint, touch, or overlap.
                if a["kind"] == b["kind"] == "segment":
                    lo, hi = sorted([float((r - p) @ u / (u @ u)), float((s - p) @ u / (u @ u))])
                    low, high = max(0, lo), min(1, hi)
                    if low > high + 1e-9:
                        return []
                    if abs(high - low) < 1e-9:
                        return [(p + low * u).tolist()]
                raise ValueError("coincident constructions have no unique finite intersection")
            return []
        t, w = cross(r - p, v) / det, cross(r - p, u) / det
        pts = [] if ((a["kind"] == "segment" and not -1e-9 <= t <= 1 + 1e-9)
                     or (b["kind"] == "segment" and not -1e-9 <= w <= 1 + 1e-9)) else [p + t * u]
    elif a["kind"] != "circle":
        pts = line_circle(a, b)
    elif b["kind"] != "circle":
        pts = line_circle(b, a)
    else:
        c, d = np.array(a["center"], float), np.array(b["center"], float)
        r, s = a["radius"], b["radius"]
        length = np.linalg.norm(d - c)
        if length < 1e-9:
            if abs(r - s) < 1e-9:
                raise ValueError("coincident circles have infinitely many intersections")
            return []
        if length > r + s + 1e-9 or length < abs(r - s) - 1e-9:
            return []
        along = (r*r - s*s + length*length) / (2 * length)
        height = np.sqrt(max(0, r*r - along*along))
        u = (d - c) / length
        middle, side = c + along * u, np.array([-u[1], u[0]]) * height
        pts = [middle] if height < 1e-8 else [middle - side, middle + side]
    return sorted([np.asarray(p).tolist() for p in pts])


def clipped_line(p, q, extent):
    """Clip an infinite line against a square without changing its direction."""
    p, q = np.asarray(p, float), np.asarray(q, float)
    d, low, high = q - p, -np.inf, np.inf
    for i in range(2):
        if abs(d[i]) < 1e-12:
            if abs(p[i]) > extent:
                return None
        else:
            lo, hi = sorted([(-extent - p[i]) / d[i], (extent - p[i]) / d[i]])
            low, high = max(low, lo), min(high, hi)
    return (p + low * d, p + high * d) if low < high else None


def plane_polygon(normal, offset, extent):
    """Intersect n·p=d with the cube, including vertical planes; ordered boundary vertices."""
    n = np.array(normal, float)
    nlen = np.linalg.norm(n)
    if not np.isfinite(nlen) or nlen < 1e-9:
        raise ValueError("plane normal must be nonzero")
    n, offset = n / nlen, offset / nlen
    verts = [np.array(v, float) for v in product([-extent, extent], repeat=3)]
    pts = []
    for i, a in enumerate(verts):
        for b in verts[i+1:]:
            if np.count_nonzero(a != b) != 1:
                continue
            da, db = a @ n - offset, b @ n - offset
            for p in ([a] if abs(da) < 1e-9 else []) + ([b] if abs(db) < 1e-9 else []):
                if not any(np.linalg.norm(p - v) < 1e-8 for v in pts):
                    pts.append(p)
            if da * db < 0:
                p = a + da / (da - db) * (b - a)
                if not any(np.linalg.norm(p - v) < 1e-8 for v in pts):
                    pts.append(p)
    if len(pts) < 3:
        raise ValueError("plane must cut a visible polygon inside the viewing cube")
    center = np.mean(pts, axis=0)
    u = pts[0] - center
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return sorted(pts, key=lambda p: np.arctan2((p-center) @ v, (p-center) @ u))


def project_3d(points, azimuth, elevation):
    """Equal-unit orthographic projection, z up. Camera position is expressed in degrees."""
    a, e = np.deg2rad([azimuth, elevation])
    basis = np.array([[-np.sin(a), np.cos(a), 0],
                      [-np.sin(e)*np.cos(a), -np.sin(e)*np.sin(a), np.cos(e)]])
    return np.asarray(points, float) @ basis.T


def surface_mesh(source, extent, density=11):
    """Wire segments in the viewing cube; break at nonfinite values, poles, and steep jumps."""
    f, edges = formula_xy(source), []
    grid = np.linspace(-extent, extent, density)
    # Sample each wire more densely than the number of wires.
    fine = np.linspace(-extent, extent, 65)
    for swap in (False, True):
        for fixed in grid:
            prev = None
            for t in fine:
                x, y = (fixed, t) if swap else (t, fixed)
                z = float(f(x, y))
                p = np.array([x, y, z])
                if not np.isfinite(z) or abs(z) > extent:
                    prev = None
                    continue
                if prev is not None and abs(z - prev[2]) < extent / 2 and f.continuous_between(prev[:2], p[:2]):
                    edges.append((prev, p))
                prev = p
    return edges


def vector_label(name, value):
    values = [f"{x:.3g}" for x in value]
    sign = "=" if all(float(t) == v for t, v in zip(values, value)) else "≈"
    return f"{name}{sign}({','.join(values)})"
