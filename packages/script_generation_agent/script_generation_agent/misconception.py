"""
The direction for a misconception clip (plan/engagement-feedback-implementation-plan.md, "Misconception clips").

A student answered a checkpoint question wrong and said they were certain: a misconception rather than a gap (Hasan et
al., 1999). The clip is the KU's usual dialogue video built around that one mistake, as a refutation: the misconception
stated, shown to fail, then the correct idea explained (Schroeder & Kucera, 2022; in video, a student voicing the
misconception and a tutor resolving it: Muller et al., 2008).
"""

from __future__ import annotations

LETTERS = "ABCDEFGH"


def misconception_focus(brief: dict) -> str:
    """The text added to the storyboard prompt. `brief` (the server's misconception_requests.brief_json): stem, options,
    correct_index, chosen, explanation."""
    options = brief["options"]
    chosen, correct = int(brief["chosen"]), int(brief["correct_index"])
    listing = "\n".join(f"  {LETTERS[i]}. {o}" for i, o in enumerate(options))
    return (
        "\n\nTHIS VIDEO ADDRESSES ONE MISCONCEPTION.\n"
        "A student answered this question about the Knowledge Unit and said they were certain of their answer:\n"
        f"Question: {brief['stem']}\n{listing}\n"
        f"They chose {LETTERS[chosen]} ({options[chosen]}). The right answer is {LETTERS[correct]} ({options[correct]}).\n"
        f"Why: {brief.get('explanation', '')}\n"
        "Build the whole video around this one mistake, as a refutation:\n"
        "- the peer states the wrong idea as their own reasoning, so the viewer sees why it seems right;\n"
        "- the explainer shows on the picture exactly where that reasoning fails;\n"
        "- then what is right, and why, with the slides' own examples and notation;\n"
        "- end with one quick case that tells the wrong idea and the right one apart.\n"
        "Do not quiz the viewer on the same question or repeat its wording, and never call anyone careless or wrong-headed: "
        "the peer's idea is a natural one to have.\n\n"
    )
