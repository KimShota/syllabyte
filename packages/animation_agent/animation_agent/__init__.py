import logging

# `import manim` imports every installed manim plugin; manim-chemistry pulls in pandas, which
# imports numexpr, and numexpr logs "NumExpr defaulting to N threads" at INFO. manim's root log
# handler prints that to stdout, ahead of the CLIs' own output. Must run before manim is imported.
logging.getLogger("numexpr").setLevel(logging.WARNING)
