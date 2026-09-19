#!/usr/bin/env python
"""
Renders runs/<run_id>/report.md — the Week-1 deliverable metrics + rubric
report: per-video KU info, critique scores, render tiers/attempts, cost and
time, plus a blank human-rubric table for you and the professor to fill in.

    uv run python scripts/report.py --run runs/dev
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from syllabyte_common.llm import PRICE_PER_MTOK
from syllabyte_common.models import (
    CritiqueResult,
    KUList,
    RenderResultList,
    RunManifest,
    Script,
)

RUBRIC_DIMENSIONS = [
    ("publishability", "0 (incorrect) - 3 (publishable) — LASEV 4-level rubric"),
    ("accuracy_vs_slides", "1-5 — does every claim match the source slides?"),
    ("pedagogical_flow", "1-5 — does it follow prepare/initiate/deliver/end sensibly?"),
    ("visual_legibility", "1-5 — is on-screen content clear on a phone screen?"),
    ("narration_naturalness", "1-5 — does the TTS narration sound natural, well-paced?"),
    ("audio_video_sync", "1-5 — do visuals and narration line up?"),
]


def load_run(run_dir: Path) -> dict:
    manifest = RunManifest.model_validate_json((run_dir / "manifest.json").read_text())
    kus = KUList.model_validate_json((run_dir / "kus.json").read_text())
    selected_ids = json.loads((run_dir / "selected_kus.json").read_text())
    by_id = {ku.id: ku for ku in kus.knowledge_units}

    videos = []
    for ku_id in selected_ids:
        ku_dir = run_dir / ku_id
        if not (ku_dir / "script.json").exists():
            videos.append({"ku_id": ku_id, "ku": by_id.get(ku_id), "incomplete": True})
            continue

        script = Script.model_validate_json((ku_dir / "script.json").read_text())
        critique = CritiqueResult.model_validate_json((ku_dir / "critique.json").read_text())

        render_results = None
        results_path = ku_dir / "render" / "render_results.json"
        if results_path.exists():
            render_results = RenderResultList.model_validate_json(results_path.read_text()).items

        diagnostics = None
        diag_path = ku_dir / "assembly_diagnostics.json"
        if diag_path.exists():
            diagnostics = json.loads(diag_path.read_text())

        videos.append({
            "ku_id": ku_id,
            "ku": by_id.get(ku_id),
            "script": script,
            "critique": critique,
            "render_results": render_results,
            "diagnostics": diagnostics,
            "incomplete": diagnostics is None,
        })

    return {"manifest": manifest, "videos": videos}


def render_report(run_dir: Path) -> str:
    data = load_run(run_dir)
    manifest: RunManifest = data["manifest"]
    videos = data["videos"]

    lines = [f"# SyllaByte Week-1 Report — {manifest.course_name or run_dir.name}", ""]
    lines.append(f"Run directory: `{run_dir}`  \nGenerated for {len(videos)} video(s).")
    lines.append("")

    # -- Per-video sections ---------------------------------------------------
    all_render_results = []
    for v in videos:
        ku = v["ku"]
        title = ku.title if ku else v["ku_id"]
        lines.append(f"## {v['ku_id']} — {title}")
        if v.get("incomplete"):
            lines.append("_(incomplete — pipeline did not finish this KU)_\n")
            continue

        script: Script = v["script"]
        critique: CritiqueResult = v["critique"]
        diagnostics = v["diagnostics"]

        lines.append(f"- Bloom's level: `{ku.bloom_level}` | cognitive load: `{ku.cognitive_load}`")
        lines.append(f"- Word count: {script.word_count} (target 150-220)")
        lines.append(f"- Critique: passed={critique.passed}, rounds={len(critique.rounds)}")
        for i, r in enumerate(critique.rounds, 1):
            lines.append(
                f"  - round {i}: coherence={r.pedagogical_coherence} "
                f"accuracy={r.conceptual_accuracy} appropriateness={r.learner_appropriateness}"
                + (f" — issues: {'; '.join(r.issues)}" if r.issues else "")
            )

        if v["render_results"]:
            lines.append("- Render tiers per segment:")
            for rr in v["render_results"]:
                all_render_results.append(rr)
                lines.append(
                    f"  - segment {rr.segment_index}: `{rr.tier}` "
                    f"({rr.attempts} attempt(s), {rr.render_seconds:.1f}s)"
                    + (f" — {rr.error}" if rr.error else "")
                )

        if diagnostics:
            lines.append(f"- Final video: `{diagnostics['final_path']}`")
            lines.append(f"- Max audio/video drift: {diagnostics['max_abs_drift_seconds']:.2f}s")

        lines.append("")

    # -- Aggregate metrics ------------------------------------------------------
    lines.append("## Aggregate metrics")
    lines.append("")
    if all_render_results:
        n = len(all_render_results)
        first_try = sum(1 for r in all_render_results if r.tier == "llm_first_try")
        repaired = sum(1 for r in all_render_results if r.tier == "llm_repaired")
        regenerated = sum(1 for r in all_render_results if r.tier == "llm_regenerated")
        fallback = sum(1 for r in all_render_results if r.tier == "template_fallback")
        llm_success = first_try + repaired + regenerated
        lines.append(f"- Segments rendered: {n}")
        lines.append(f"- Render success rate (LLM code, any tier): {llm_success}/{n} ({100 * llm_success / n:.0f}%)")
        lines.append(f"- First-try success rate: {first_try}/{n} ({100 * first_try / n:.0f}%)")
        lines.append(f"- Needed Tier-1 repair: {repaired}/{n}")
        lines.append(f"- Needed Tier-2 regeneration: {regenerated}/{n}")
        lines.append(f"- Fell back to a deterministic template: {fallback}/{n}")
        lines.append("")

    total_cost = manifest.total_cost_usd(PRICE_PER_MTOK)
    total_wall = sum(c.wall_seconds for c in manifest.llm_calls)
    lines.append(f"- Total LLM calls: {len(manifest.llm_calls)}")
    lines.append(f"- Total LLM wall time: {total_wall:.1f}s")
    lines.append(f"- Estimated LLM cost: ${total_cost:.2f}")
    if videos:
        n_complete = sum(1 for v in videos if not v.get("incomplete"))
        if n_complete:
            lines.append(f"- Est. cost per completed video: ${total_cost / n_complete:.2f}")
    lines.append("")

    by_stage: dict[str, int] = {}
    for call in manifest.llm_calls:
        by_stage[call.stage] = by_stage.get(call.stage, 0) + call.input_tokens + call.output_tokens
    if by_stage:
        lines.append("### Token usage by stage")
        for stage, tokens in sorted(by_stage.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {stage}: {tokens:,} tokens")
        lines.append("")

    # -- Human rubric (blank, to fill in) ---------------------------------------
    lines.append("## Human review rubric")
    lines.append("")
    lines.append(
        "Fill in one row per video (you first, then the professor). Scale per "
        "dimension is noted in the header."
    )
    lines.append("")
    header = "| video | " + " | ".join(f"{name} ({desc.split('—')[0].strip()})" for name, desc in RUBRIC_DIMENSIONS) + " | notes |"
    sep = "|" + "---|" * (len(RUBRIC_DIMENSIONS) + 2)
    lines.append(header)
    lines.append(sep)
    for v in videos:
        lines.append(f"| {v['ku_id']} | " + " | ".join([""] * len(RUBRIC_DIMENSIONS)) + " | |")
    lines.append("")
    lines.append("Dimension definitions:")
    for name, desc in RUBRIC_DIMENSIONS:
        lines.append(f"- **{name}**: {desc}")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="Path to the run directory (e.g. runs/dev)")
    args = parser.parse_args()

    run_dir = Path(args.run)
    report = render_report(run_dir)
    out_path = run_dir / "report.md"
    out_path.write_text(report)
    print(f"Wrote {out_path}")
