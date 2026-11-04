"""
Semantic Critique sub-agent — Component 3, Week-1 scope.

Scores a generated script against the slides it's grounded in on four
dimensions (pedagogical coherence, conceptual accuracy, learner
appropriateness, visual alignment of each beat's visual with its sentence).
If any score falls below CRITIQUE_THRESHOLD, the caller
(write_script_with_critique) regenerates with the critique text appended as
a revision instruction, up to MAX_ROUNDS total attempts.
"""

from __future__ import annotations

from script_generation_agent.prompts import (
    CRITIQUE_SYSTEM_PROMPT,
    build_critique_prompt,
    critique_system_prompt,
    dialogue_critique_system_prompt,
)
from script_generation_agent.script_writer import (
    Style,
    Visuals,
    add_draws,
    gather_source_material,
    write_script,
)
from syllabyte_common.llm import DEFAULT_MODEL, structured, text_block
from syllabyte_common.models import (
    CourseCorpus,
    CritiqueResult,
    CritiqueScore,
    KnowledgeUnit,
    RunManifest,
    Script,
)

CRITIQUE_THRESHOLD = 7
MAX_ROUNDS = 2


def critique(
    script: Script,
    corpus: CourseCorpus,
    ku: KnowledgeUnit,
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
    system: str = CRITIQUE_SYSTEM_PROMPT,
    stage: str = "critique",
) -> CritiqueScore:
    """Scores `script` (or a BaseScript, which has the same shape) against the slides it cites."""
    # The critic sees the same slides the writer saw: text and slide images. With text alone it
    # marks anything shown only in a diagram as invented and forces a needless rewrite.
    text_context, image_blocks = gather_source_material(corpus, ku)
    prompt = build_critique_prompt(script.model_dump_json(indent=2), text_context, has_images=bool(image_blocks))

    return structured(
        schema=CritiqueScore,
        content=[text_block(prompt), *image_blocks],
        system=system,
        stage=stage,
        ku_id=ku.id,
        model=model,
        max_tokens=16000,  # a dialogue critique with many issues ran past 4000
        manifest=manifest,
    )


_ORDINALS = {"first": 0, "second": 1, "third": 2, "1": 0, "2": 1, "3": 2}


def issues_by_segment(script: Script, issues: list[str]) -> dict[int, list[str]]:
    """Segment index -> the critic's issues that name that segment's phase ("deliver (second segment), beat 3",
    "end, beat 2"), so a redraw changes only the segments with problems and each drawer sees only its own. An
    issue naming one of several segments of a phase without saying which goes to all of them; one naming no
    phase (pacing, slang) is about the words and is left out. Every segment, with every issue, if none match."""
    import re

    phases = [seg.phase for seg in script.segments]
    out: dict[int, list[str]] = {}
    for issue in issues:
        low = issue.lower()
        hits = []
        for phase in dict.fromkeys(phases):
            if not re.search(rf"\b{phase}\b", low):
                continue
            same = [i for i, p in enumerate(phases) if p == phase]
            which = re.search(rf"\b{phase}\b[^,;:]*?\b(first|second|third|segment \d|-\d)\b|"
                              rf"\b(first|second|third)\s+{phase}\b", low)
            if len(same) > 1 and which:
                word = next(g for g in which.groups() if g).replace("segment ", "").lstrip("-")
                k = _ORDINALS.get(word)
                same = [same[k]] if k is not None and k < len(same) else same
            hits += same
        for i in dict.fromkeys(hits):
            out.setdefault(i, []).append(issue)
    return out or {i: list(issues) for i in range(len(phases))}


def write_script_with_critique(
    ku: KnowledgeUnit,
    corpus: CourseCorpus,
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
    skip_critic: bool = False,
    level: int | None = None,
    prereq_titles: list[str] | None = None,
    style: Style = "monologue",
    visuals: Visuals = "codegen",
    on_lines_ready=None,
) -> tuple[Script, CritiqueResult]:
    """Writes a script, critiques it, and regenerates (up to MAX_ROUNDS-1
    additional times) if any critique score falls below threshold. With
    `level`, both the script and the critic's idea of "appropriate" are for
    that level. `on_lines_ready` is passed to write_script: it is called each
    time a script's lines pass the checks (the voices can start then)."""
    result = CritiqueResult(ku_id=ku.id)
    extra_instruction = ""
    script: Script | None = None
    system = CRITIQUE_SYSTEM_PROMPT if level is None else critique_system_prompt(level)
    stage = "critique" if level is None else f"critique_l{level}"
    if style == "dialogue":
        from syllabyte_common.cast import load_cast

        cast = load_cast()
        system = dialogue_critique_system_prompt(level or 2, explainer=cast.explainer.name, peer=cast.peer.name)
        stage = f"critique_dialogue_l{level}"

    redraw: list[str] = []  # the critic's issues, when only the pictures need another go
    for round_num in range(1, MAX_ROUNDS + 1):
        if redraw and script is not None:
            # Template visuals: the lines passed and only the pictures scored low, so draw again with the
            # critic's issues (a few parallel calls) instead of rewriting the script (plan phase 3 finding).
            script = add_draws(script, ku_id=ku.id, manifest=manifest,
                               feedback=issues_by_segment(script, redraw))
        else:
            script = write_script(
                ku, corpus, model=model, manifest=manifest, extra_instruction=extra_instruction,
                level=level, prereq_titles=prereq_titles, style=style, visuals=visuals,
                on_lines_ready=on_lines_ready,
            )

        if skip_critic:
            result.passed = True
            return script, result

        score = critique(script, corpus, ku, model=model, manifest=manifest, system=system, stage=stage)
        result.rounds.append(score)

        if score.min_score >= CRITIQUE_THRESHOLD:
            result.passed = True
            return script, result

        text_ok = min(score.pedagogical_coherence, score.conceptual_accuracy,
                      score.learner_appropriateness) >= CRITIQUE_THRESHOLD
        redraw = score.issues if visuals == "templates" and text_ok else []
        if round_num < MAX_ROUNDS and not redraw:
            extra_instruction = (
                "The previous script scored below threshold. Issues found:\n"
                + "\n".join(f"- {issue}" for issue in score.issues)
                + "\nFix these issues in the new script."
            )

    # Exhausted rounds without passing threshold — return the last attempt
    # anyway (Week-1 scope: flag it in the report rather than blocking the
    # pipeline entirely).
    assert script is not None
    return script, result


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from syllabyte_common.models import CourseCorpus as _Corpus
    from syllabyte_common.models import KUList

    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--kus", required=True)
    parser.add_argument("--ku-id", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--level", type=int, choices=[1, 2, 3], default=None, help="write for one student's level on this KU")
    parser.add_argument("--style", choices=["monologue", "dialogue"], default="monologue", help="dialogue: two characters (needs --level)")
    parser.add_argument("--visuals", choices=["codegen", "templates"], default="codegen",
                        help="templates: draw lines with the visual template library (dialogue only)")
    args = parser.parse_args()

    corpus = _Corpus.model_validate_json(Path(args.corpus).read_text())
    kus = KUList.model_validate_json(Path(args.kus).read_text())
    ku = next(k for k in kus.knowledge_units if k.id == args.ku_id)

    manifest = RunManifest(run_id="cli")
    prereqs = [k.title for k in kus.knowledge_units if k.id in ku.prerequisites]
    script, result = write_script_with_critique(
        ku, corpus, manifest=manifest, level=args.level, prereq_titles=prereqs, style=args.style,
        visuals=args.visuals,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = (f".L{args.level}" if args.level else "") + (".dialogue" if args.style == "dialogue" else "")
    suffix += ".templates" if args.visuals == "templates" else ""
    (out_dir / f"script{suffix}.json").write_text(script.model_dump_json(indent=2))
    (out_dir / f"critique{suffix}.json").write_text(result.model_dump_json(indent=2))
    (out_dir / f"manifest{suffix}.json").write_text(manifest.model_dump_json(indent=2))

    print(f"Script for {ku.id}: {script.word_count} words, passed={result.passed}")
    for i, r in enumerate(result.rounds, 1):
        print(f"  round {i}: coherence={r.pedagogical_coherence} accuracy={r.conceptual_accuracy} "
              f"appropriateness={r.learner_appropriateness} visual_alignment={r.visual_alignment}")
    for c in manifest.llm_calls:
        print(f"  {c.stage:18s} {c.wall_seconds:6.1f}s  out {c.output_tokens:>6,} tokens")
    from syllabyte_common.llm import PRICE_PER_MTOK

    print(f"LLM cost ≈ ${manifest.total_cost_usd(PRICE_PER_MTOK):.2f}")
