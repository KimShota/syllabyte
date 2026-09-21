"""
Semantic Critique sub-agent — Component 3, Week-1 scope.

Scores a generated script against the slides it's grounded in on three
dimensions (pedagogical coherence, conceptual accuracy, learner
appropriateness). If any score falls below CRITIQUE_THRESHOLD, the caller
(write_script_with_critique) regenerates with the critique text appended as
a revision instruction, up to MAX_ROUNDS total attempts.
"""

from __future__ import annotations

from script_generation_agent.prompts import CRITIQUE_SYSTEM_PROMPT, build_critique_prompt
from script_generation_agent.script_writer import gather_source_material, write_script
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
) -> CritiqueScore:
    text_context, _ = gather_source_material(corpus, ku)
    prompt = build_critique_prompt(script.model_dump_json(indent=2), text_context)

    return structured(
        schema=CritiqueScore,
        content=[text_block(prompt)],
        system=CRITIQUE_SYSTEM_PROMPT,
        stage="critique",
        ku_id=ku.id,
        model=model,
        max_tokens=4000,
        manifest=manifest,
    )


def write_script_with_critique(
    ku: KnowledgeUnit,
    corpus: CourseCorpus,
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
    skip_critic: bool = False,
) -> tuple[Script, CritiqueResult]:
    """Writes a script, critiques it, and regenerates (up to MAX_ROUNDS-1
    additional times) if any critique score falls below threshold."""
    result = CritiqueResult(ku_id=ku.id)
    extra_instruction = ""
    script: Script | None = None

    for round_num in range(1, MAX_ROUNDS + 1):
        script = write_script(
            ku, corpus, model=model, manifest=manifest, extra_instruction=extra_instruction
        )

        if skip_critic:
            result.passed = True
            return script, result

        score = critique(script, corpus, ku, model=model, manifest=manifest)
        result.rounds.append(score)

        if score.min_score >= CRITIQUE_THRESHOLD:
            result.passed = True
            return script, result

        if round_num < MAX_ROUNDS:
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
    args = parser.parse_args()

    corpus = _Corpus.model_validate_json(Path(args.corpus).read_text())
    kus = KUList.model_validate_json(Path(args.kus).read_text())
    ku = next(k for k in kus.knowledge_units if k.id == args.ku_id)

    manifest = RunManifest(run_id="cli")
    script, result = write_script_with_critique(ku, corpus, manifest=manifest)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "script.json").write_text(script.model_dump_json(indent=2))
    (out_dir / "critique.json").write_text(result.model_dump_json(indent=2))

    print(f"Script for {ku.id}: {script.word_count} words, passed={result.passed}")
    for i, r in enumerate(result.rounds, 1):
        print(f"  round {i}: coherence={r.pedagogical_coherence} accuracy={r.conceptual_accuracy} "
              f"appropriateness={r.learner_appropriateness}")
