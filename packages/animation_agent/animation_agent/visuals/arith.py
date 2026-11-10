"""Exact arithmetic for checking the numbers a picture writes.

A writer types facts into some templates by hand: a formula line (`\\gcd(18, 24) = 6`), a number-line point named
"1/2", a table column headed "n^2". This evaluates the closed, numeric parts of these so the checks in specs.py can
reject a false one. Anything it doesn't understand (a variable without a value, words, an unknown command) raises
NotNumeric, and the checks then leave the text alone: they only reject what they can prove wrong.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction

Number = Fraction | float

MAX_FACTORIAL = 170
MAX_POWER_BITS = 4096


class NotNumeric(ValueError):
    """The text isn't a closed numeric expression this module can evaluate."""


# --------------------------------------------------------------------------
# Plain expressions: "n^2", "n log n", "2^n", "n(n+1)/2", "√2", "1/2"
# --------------------------------------------------------------------------

_TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?|\.\d+)|([A-Za-z_][A-Za-z0-9_]*)|(\*\*|[-+*/^%!(),]))")
_UNICODE = {"²": "^2", "³": "^3", "√": " sqrt ", "×": "*", "·": "*", "⋅": "*", "÷": "/", "−": "-", "π": " pi ",
            "₂": "2", "⌊": " floor(", "⌋": ")", "⌈": " ceil(", "⌉": ")"}
_FUNCS = {"sqrt", "gcd", "lcm", "binom", "floor", "ceil", "log", "log2", "lg", "ln", "log10", "abs"}
_CONSTS = {"pi": math.pi}


def _tokens(text: str) -> list[tuple[str, str]]:
    for k, v in _UNICODE.items():
        text = text.replace(k, v)
    out, i = [], 0
    while i < len(text):
        m = _TOKEN.match(text, i)
        if not m or m.end() == i:
            if text[i:].strip() == "":
                break
            raise NotNumeric(f"can't read {text[i:]!r}")
        num, name, op = m.groups()
        if num is not None:
            out.append(("num", num))
        elif name is not None:
            out.append(("name", name))
        elif op is not None:
            out.append(("op", "^" if op == "**" else op))
        i = m.end()
    return out


def _int(x: Number, what: str) -> int:
    if isinstance(x, Fraction) and x.denominator == 1:
        return int(x)
    if isinstance(x, float) and x.is_integer():
        return int(x)
    raise NotNumeric(f"{what} needs whole numbers")


def _power(base: Number, exp: Number) -> Number:
    if isinstance(exp, Fraction) and exp.denominator == 1:
        e = int(exp)
        if isinstance(base, Fraction):
            bits = max(abs(base.numerator), abs(base.denominator), 2).bit_length()
            if abs(e) * bits > MAX_POWER_BITS:
                raise NotNumeric("too large to check")
            if base == 0 and e < 0:
                raise NotNumeric("division by zero")
            return base ** e
    try:
        out = float(base) ** float(exp)
    except (OverflowError, ZeroDivisionError) as e:
        raise NotNumeric(str(e)) from None
    if isinstance(out, complex) or math.isinf(out) or math.isnan(out):
        raise NotNumeric("not a real number")
    return out


def _call(name: str, args: list[Number], log_base: float | None) -> Number:
    def one() -> Number:
        if len(args) != 1:
            raise NotNumeric(f"{name} takes one argument")
        return args[0]

    if name == "sqrt":
        x = one()
        if x < 0:
            raise NotNumeric("square root of a negative number")
        if isinstance(x, Fraction):
            n, d = math.isqrt(x.numerator), math.isqrt(x.denominator)
            if n * n == x.numerator and d * d == x.denominator:
                return Fraction(n, d)
        return math.sqrt(x)
    if name in ("gcd", "lcm"):
        if len(args) < 2:
            raise NotNumeric(f"{name} takes two or more numbers")
        ints = [_int(a, name) for a in args]
        return Fraction(math.gcd(*ints) if name == "gcd" else math.lcm(*ints))
    if name == "binom":
        if len(args) != 2:
            raise NotNumeric("binom takes n and k")
        n, k = (_int(a, "binom") for a in args)
        if not 0 <= n <= 1000:
            raise NotNumeric("binom out of range")
        return Fraction(math.comb(n, k) if 0 <= k else 0)
    if name in ("floor", "ceil"):
        x = one()
        return Fraction(math.floor(x) if name == "floor" else math.ceil(x))
    if name == "abs":
        return abs(one())
    x = one()
    base = {"log2": 2, "lg": 2, "ln": math.e, "log10": 10}.get(name, log_base)
    if base is None:
        raise NotNumeric("a log without a base")
    if x <= 0:
        raise NotNumeric("log of a number 0 or less")
    if isinstance(x, Fraction) and base in (2, 10) and x.denominator == 1:  # exact when it is a whole power
        k = round(math.log(x, base))
        if base ** k == x:
            return Fraction(k)
    return math.log(x) / math.log(base)


class _Parser:
    """Recursive descent over the tokens: + - (lowest), * / % and juxtaposition ("2n", "n log n"), unary minus,
    ^ (right to left), postfix !, then numbers, names, calls and brackets."""

    def __init__(self, tokens, names: dict[str, Number], log_base: float | None):
        self.t, self.i, self.names, self.log_base = tokens, 0, names, log_base

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self, value: str | None = None):
        kind, v = self.peek()
        if kind is None or (value is not None and v != value):
            raise NotNumeric(f"expected {value or 'more'}")
        self.i += 1
        return kind, v

    def parse(self) -> Number:
        out = self.expr()
        if self.i != len(self.t):
            raise NotNumeric(f"can't read past {self.t[self.i][1]!r}")
        return out

    def expr(self) -> Number:
        out = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            rhs = self.term()
            out = out + rhs if op == "+" else out - rhs
        return out

    def _starts_operand(self) -> bool:
        kind, v = self.peek()
        return kind in ("num", "name") or (kind, v) == ("op", "(")

    def term(self) -> Number:
        out = self.unary()
        while True:
            kind, v = self.peek()
            if (kind, v) in (("op", "*"), ("op", "/"), ("op", "%")):
                self.take()
                rhs = self.unary()
                if v == "*":
                    out = out * rhs
                elif rhs == 0:
                    raise NotNumeric("division by zero")
                elif v == "/":
                    out = out / rhs
                else:
                    out = Fraction(_int(out, "mod") % _int(rhs, "mod"))
            elif self._starts_operand():
                if self.t[self.i - 1][0] == "num" and kind == "num":
                    raise NotNumeric("two numbers side by side")
                out = out * self.power()
            else:
                return out

    def unary(self) -> Number:
        if self.peek() == ("op", "-"):
            self.take()
            return -self.unary()
        if self.peek() == ("op", "+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self) -> Number:
        base = self.postfix()
        if self.peek() == ("op", "^"):
            self.take()
            return _power(base, self.unary())
        return base

    def postfix(self) -> Number:
        out = self.atom()
        while self.peek() == ("op", "!"):
            self.take()
            n = _int(out, "a factorial")
            if not 0 <= n <= MAX_FACTORIAL:
                raise NotNumeric("factorial out of range")
            out = Fraction(math.factorial(n))
        return out

    def atom(self) -> Number:
        kind, v = self.take()
        if kind == "num":
            return Fraction(v)
        if (kind, v) == ("op", "("):
            out = self.expr()
            self.take(")")
            return out
        if kind == "name":
            if v in _FUNCS:
                if self.peek() == ("op", "("):
                    self.take()
                    args = [self.expr()]
                    while self.peek() == ("op", ","):
                        self.take()
                        args.append(self.expr())
                    self.take(")")
                else:  # "log n", "sqrt 2": the next operand, without its juxtaposed neighbours
                    args = [self.power()]
                return _call(v, args, self.log_base)
            if v in self.names:
                return self.names[v]
            if v in _CONSTS:
                return _CONSTS[v]
            raise NotNumeric(f"{v!r} has no value")
        raise NotNumeric(f"unexpected {v!r}")


def evaluate(text: str, names: dict[str, Number] | None = None, log_base: float | None = None) -> Number:
    """The value of a plain expression ("n^2", "2^10", "n log n", "gcd(18, 24)"); names give variables values.
    A log without a base uses log_base, or raises NotNumeric."""
    return _Parser(_tokens(text), names or {}, log_base).parse()


def names_in(text: str) -> set[str]:
    """The variable names an expression uses (not its functions or constants); empty if it isn't readable."""
    try:
        toks = _tokens(text)
    except NotNumeric:
        return set()
    return {v for k, v in toks if k == "name" and v not in _FUNCS and v not in _CONSTS}


# --------------------------------------------------------------------------
# A written value matches a computed one
# --------------------------------------------------------------------------

_DECIMAL = re.compile(r"^\s*-?\d*\.(\d+)\s*$")


def matches(value: Number, written: str, written_value: Number | None = None) -> bool:
    """Whether a value written as `written` (a number, or an expression worth written_value) is `value`. A decimal
    written with d places may be rounded or cut off at its last place (2/3 as 0.67 or 0.66, not 0.65)."""
    if written_value is None:
        written_value = evaluate(written)
    if m := _DECIMAL.match(written):
        unit, v, w = 10.0 ** -len(m.group(1)), float(value), float(written_value)
        rounded = abs(v - w) <= unit / 2 + 1e-12
        cut_off = (v >= 0) == (w >= 0) and -1e-12 <= abs(v) - abs(w) < unit
        return rounded or cut_off
    if isinstance(value, Fraction) and isinstance(written_value, Fraction):
        return value == written_value
    return math.isclose(float(value), float(written_value), rel_tol=1e-9, abs_tol=1e-12)


def show(x: Number) -> str:
    """A value as a check's message writes it: 6, 3/4, 1.414."""
    if isinstance(x, Fraction):
        return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"
    return f"{x:.6g}"


# --------------------------------------------------------------------------
# TeX formulas: each relation between closed numeric sides is checked
# --------------------------------------------------------------------------

# Splits one formula into separate statements ("a = 3 \quad b = 4", "x = 2 \Rightarrow y = 4").
_STATEMENT_BREAK = re.compile(r"\\(?:Rightarrow|Leftarrow|Leftrightarrow|implies|impliedby|iff|to|qquad|quad)"
                              r"(?![A-Za-z])|\\(?:text|mathrm)\s*\{(?!\s*(?:gcd|lcm|mod)\s*\})[^{}]*\}|;")
_RELATION = re.compile(r"\\(?:neq|ne|leq|le|geq|ge|equiv|approx|sim|cong)(?![A-Za-z])|=|<|>")
_MODULUS = re.compile(r"(?:\\pmod\s*\{([^{}]*)\}|\\pmod\s*(\d+)|\(\s*\\(?:bmod|mod)\s*([^()]*)\)|\\mod\s*\{?(\d+)\}?)"
                      r"\s*$")
_DROP = re.compile(r"\\(?:left|right|displaystyle|textstyle|big|Big|bigg|Bigg)(?![A-Za-z])|\\[,;:! ]|~|&")
_SIMPLE = {r"\cdot": "*", r"\times": "*", r"\ast": "*", r"\div": "/", r"\bmod": "%", r"\mod": "%",
           r"\gcd": "gcd", r"\lcm": "lcm", r"\ln": "ln", r"\lg": "lg", r"\pi": "pi", r"\lfloor": "floor(",
           r"\rfloor": ")", r"\lceil": "ceil(", r"\rceil": ")", r"\%": "/100", r"\infty": "@"}


def _group(tex: str, i: int) -> tuple[str, int]:
    """The braced group (or single character) at tex[i], and the index after it."""
    while i < len(tex) and tex[i] == " ":
        i += 1
    if i >= len(tex):
        raise NotNumeric("a command is missing its argument")
    if tex[i] != "{":
        if tex[i] == "\\":
            m = re.match(r"\\[A-Za-z]+", tex[i:])
            if m:
                return m.group(0), i + m.end()
        return tex[i], i + 1
    depth = 0
    for j in range(i, len(tex)):
        depth += {"{": 1, "}": -1}.get(tex[j], 0)
        if depth == 0:
            return tex[i + 1:j], j + 1
    raise NotNumeric("unbalanced braces")


def tex_to_plain(tex: str) -> str:
    """A TeX formula side as a plain expression evaluate() reads: \\frac{a}{b} -> ((a)/(b)), \\binom, \\sqrt,
    \\gcd, \\log_2, ^{..}; anything else with a backslash raises NotNumeric."""
    tex = re.sub(r"(\d)(?:\{,\}|\\,)(?=\d{3}(?!\d))", r"\1", tex)  # 1{,}000 and 1\,000: thousands
    tex = _DROP.sub(" ", tex)
    out, i = [], 0
    while i < len(tex):
        ch = tex[i]
        if ch == "\\":
            m = re.match(r"\\([A-Za-z]+)", tex[i:])
            if not m:
                raise NotNumeric(f"can't read {tex[i:i + 2]!r}")
            cmd, i = m.group(1), i + m.end()
            if cmd in ("frac", "dfrac", "tfrac", "binom", "dbinom", "tbinom"):
                a, i = _group(tex, i)
                b, i = _group(tex, i)
                a, b = tex_to_plain(a), tex_to_plain(b)
                out.append(f"(({a})/({b}))" if "frac" in cmd else f"binom(({a}),({b}))")
            elif cmd == "sqrt":
                if tex[i:i + 1] == "[":
                    raise NotNumeric("an nth root")
                a, i = _group(tex, i)
                out.append(f"sqrt({tex_to_plain(a)})")
            elif cmd in ("boxed", "mathbf", "mathrm", "operatorname", "text", "textbf", "mathit"):
                a, i = _group(tex, i)
                if cmd in ("boxed", "mathbf"):
                    out.append(f"({tex_to_plain(a)})")
                elif a.strip() in ("gcd", "lcm", "mod"):
                    out.append({"mod": "%"}.get(a.strip(), a.strip()))
                else:
                    raise NotNumeric(f"words: {a!r}")
            elif cmd == "log":
                rest = tex[i:].lstrip()
                if rest.startswith("_"):
                    base, i = _group(tex, tex.index("_", i) + 1)
                    out.append({"2": " log2 ", "10": " log10 "}.get(base.strip(), " logb(0) "))
                else:
                    out.append(" log ")
            elif f"\\{cmd}" in _SIMPLE:
                out.append(f" {_SIMPLE[chr(92) + cmd]} ")
            else:
                raise NotNumeric(f"\\{cmd}")
        elif ch in "{[":
            out.append("(")
            i += 1
        elif ch in "}]":
            out.append(")")
            i += 1
        elif ch == "_":
            raise NotNumeric("a subscript")
        elif ch == "'":
            raise NotNumeric("a prime")
        else:
            out.append(ch)
            i += 1
    plain = "".join(out)
    if "@" in plain or "logb(" in plain:
        raise NotNumeric("not a plain number")
    return plain


def _side(tex: str) -> tuple[Number, str]:
    plain = tex_to_plain(tex)
    return evaluate(plain), plain


def _holds(rel: str, a: Number, b: Number, b_text: str, a_text: str) -> bool:
    if rel == "=":
        return matches(b, a_text, a) if _DECIMAL.match(a_text) else matches(a, b_text, b)
    if rel in (r"\neq", r"\ne"):
        return not _holds("=", a, b, b_text, a_text)
    fa, fb = float(a), float(b)
    return {"<": fa < fb, ">": fa > fb, r"\le": fa <= fb, r"\leq": fa <= fb, r"\ge": fa >= fb,
            r"\geq": fa >= fb}[rel]


_REL_WORDS = {"=": "=", r"\neq": "≠", r"\ne": "≠", "<": "<", ">": ">", r"\le": "≤", r"\leq": "≤", r"\ge": "≥",
              r"\geq": "≥", r"\equiv": "≡"}


def false_relation(tex: str) -> str | None:
    """Why a formula is false, if one of its relations joins two closed numeric sides that don't satisfy it
    (`\\gcd(18, 24) = 4`, `2^{10} = 1000`, `17 \\equiv 3 \\pmod{5}`); None if every such relation holds or nothing
    in it is numeric. Rounded decimals pass (`\\sqrt{2} = 1.414`); \\approx is never checked."""
    while (at := tex.find(r"\boxed")) >= 0:  # a boxed result is checked like the rest
        try:
            inner, end = _group(tex, at + len(r"\boxed"))
        except NotNumeric:
            return None
        tex = f"{tex[:at]} {inner} {tex[end:]}"
    for statement in _STATEMENT_BREAK.split(tex):
        modulus = None
        if r"\equiv" in statement and (m := _MODULUS.search(statement)):
            try:
                modulus = _int(_side(next(g for g in m.groups() if g is not None))[0], "a modulus")
            except NotNumeric:
                modulus = None
            statement = statement[:m.start()]
        parts = _RELATION.split(statement)
        rels = _RELATION.findall(statement)
        for left, rel, right in zip(parts, rels, parts[1:], strict=False):
            if rel in (r"\approx", r"\sim", r"\cong") or (rel == r"\equiv" and not modulus):
                continue
            try:
                a, a_plain = _side(left)
                b, b_plain = _side(right)
                if rel == r"\equiv":
                    ok = (_int(a, "mod") - _int(b, "mod")) % modulus == 0
                else:
                    ok = _holds(rel, a, b, b_plain.strip(), a_plain.strip())
            except (NotNumeric, ZeroDivisionError, OverflowError, TypeError):
                continue
            if not ok:
                lhs, rhs = left.strip(), right.strip()
                if rel == r"\equiv":
                    return (f"{lhs} ≡ {rhs} (mod {modulus}) is false: {show(a)} and {show(b)} leave remainders "
                            f"{_int(a, 'mod') % modulus} and {_int(b, 'mod') % modulus}")
                if rel == "=":
                    if re.fullmatch(r"-?\d+(?:\.\d+)?", rhs.replace(" ", "")):
                        return f"{lhs} = {rhs} is false: {lhs} is {show(a)}, not {rhs}"
                    return f"{lhs} = {rhs} is false: {lhs} is {show(a)}, but {rhs} is {show(b)}"
                return f"{lhs} {_REL_WORDS[rel]} {rhs} is false: {show(a)} {_REL_WORDS[rel]} {show(b)} doesn't hold"
    return None
