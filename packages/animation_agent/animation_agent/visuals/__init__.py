"""
The visual template library (plan/visual-template-library-plan.md).

The script writer draws each line with a few calls on tested templates, written in the script itself:

    arr = ArrayBars(values=[1, 3, 4, 7, 9, 11, 15], area="bottom_half")
    arr.bisect_check(target=9)

Instead of an LLM writing Manim code for the segment, this package draws those calls.
  - specs.py     what each template takes and can do (no Manim import, so the script writer can check calls)
  - calls.py     parsing and checking a segment's calls (no Manim import)
  - primitives.py, base.py, the template modules: the drawing
  - runner.py    plays one beat's calls inside a GridLayoutScene, timed to the beat's narration
  - scene_code.py  the scene file the renderer runs for a segment drawn from calls
"""
