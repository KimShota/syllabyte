#!/usr/bin/env python
"""
End-to-end Week-1 orchestrator: syllabus + slides -> short-form videos.

    uv run python scripts/generate_shorts.py \\
        --syllabus data/courses/cs101/syllabus.pdf \\
        --slides data/courses/cs101/slides/*.pdf \\
        --n-videos 3 --quality low --out runs/dev

Every stage's output is written to runs/<run_id>/ as JSON (or media files)
per syllabyte_common.run_store.RunDir, so a re-run with --from-stage picks
up from any stage instead of recomputing everything. Stage order:

    ingest -> extract_kus -> script -> tts -> animate -> assemble

Within a KU, a stage is skipped automatically if its output already exists
on disk UNLESS --from-stage explicitly names that stage or an earlier one
(which forces recomputation of everything from that point on).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Make the sibling `packages/*/…` dirs importable when run via `uv run
# python scripts/generate_shorts.py` without a full `uv sync` editable
# install path issue — harmless no-op once the packages are installed.
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion_agent.corpus import build_corpus
from curriculum_alignment_agent.ku_extractor import extract_kus, select_kus
from script_generation_agent.critic import write_script_with_critique
from animation_agent.tts import build_srt, concat_wavs, synthesize_segments
from animation_agent.renderer import render_segment
from animation_agent.assemble import assemble_ku_video
from syllabyte_common.models import (
    CourseCorpus,
    KnowledgeUnit,
    KUList,
    RenderResultList,
    RunManifest,
    Script,
    SegmentAudioList,
)
from syllabyte_common.run_store import RunDir, new_run_id

STAGES = ["ingest", "extract_kus", "script", "tts", "animate", "assemble"]


def stage_index(name: str) -> int:
    return STAGES.index(name)


def log(msg: str) -> None:
    print(f"[generate_shorts] {msg}", flush=True)


def run(args: argparse.Namespace) -> None:
    run_dir = RunDir(args.out)
    force_from = stage_index(args.from_stage) if args.from_stage else len(STAGES)

    manifest_path = "manifest.json"
    manifest = (
        run_dir.load_json(manifest_path, RunManifest)
        if run_dir.exists(manifest_path) and force_from > stage_index("ingest")
        else RunManifest(run_id=new_run_id())
    )

    # -- Stage 1: ingest -----------------------------------------------------
    if force_from <= stage_index("ingest") or not run_dir.exists("corpus.json"):
        log(f"[1/6] ingest: {args.syllabus} + {len(args.slides)} deck(s)")
        corpus = build_corpus(args.syllabus, args.slides, run_dir.root / "images")
        run_dir.save_json("corpus.json", corpus)
    else:
        log("[1/6] ingest: reusing existing corpus.json")
        corpus = run_dir.load_json("corpus.json", CourseCorpus)
    manifest.course_name = corpus.course_name
    run_dir.save_json(manifest_path, manifest)

    # -- Stage 2: extract_kus -------------------------------------------------
    if force_from <= stage_index("extract_kus") or not run_dir.exists("kus.json"):
        log("[2/6] extract_kus: calling Claude per deck")
        kus = extract_kus(corpus, manifest=manifest)
        run_dir.save_json("kus.json", kus)
        run_dir.save_json(manifest_path, manifest)
    else:
        log("[2/6] extract_kus: reusing existing kus.json")
        kus = run_dir.load_json("kus.json", KUList)

    if args.ku_ids:
        by_id = {ku.id: ku for ku in kus.knowledge_units}
        missing = [kid for kid in args.ku_ids if kid not in by_id]
        if missing:
            raise SystemExit(f"--ku-ids not found in kus.json: {missing}")
        selected: list[KnowledgeUnit] = [by_id[kid] for kid in args.ku_ids]
    else:
        selected = select_kus(kus, args.n_videos)

    log(f"Selected {len(selected)} KU(s): {[k.id for k in selected]}")
    run_dir.path("selected_kus.json").write_text(
        json.dumps([k.id for k in selected], indent=2)
    )

    # -- Per-KU stages: script -> tts -> animate -> assemble ------------------
    for ku in selected:
        log(f"--- KU: {ku.id} ({ku.title}) ---")
        ku_dir = run_dir.ku_dir(ku.id)

        # Stage 3: script + critique
        script_path = ku_dir / "script.json"
        critique_path = ku_dir / "critique.json"
        if force_from <= stage_index("script") or not script_path.exists():
            log(f"[3/6] script: writing + critiquing script for {ku.id}")
            script, critique_result = write_script_with_critique(
                ku, corpus, manifest=manifest, skip_critic=args.skip_critic
            )
            script_path.write_text(script.model_dump_json(indent=2))
            critique_path.write_text(critique_result.model_dump_json(indent=2))
            run_dir.save_json(manifest_path, manifest)
        else:
            log(f"[3/6] script: reusing existing script for {ku.id}")
            script = Script.model_validate_json(script_path.read_text())

        # Stage 4: TTS
        audio_dir = ku_dir / "audio"
        audio_manifest_path = audio_dir / "segment_audio.json"
        if force_from <= stage_index("tts") or not audio_manifest_path.exists():
            log(f"[4/6] tts: synthesizing narration ({args.tts})")
            segment_audios = synthesize_segments(script, audio_dir, backend_name=args.tts)
            audio_dir.mkdir(parents=True, exist_ok=True)
            audio_manifest_path.write_text(
                SegmentAudioList(items=segment_audios).model_dump_json(indent=2)
            )
            concat_wavs(segment_audios, audio_dir / "narration.wav")
            build_srt(script, segment_audios, audio_dir / "captions.srt")
        else:
            log(f"[4/6] tts: reusing existing audio for {ku.id}")
            segment_audios = SegmentAudioList.model_validate_json(
                audio_manifest_path.read_text()
            ).items

        # Stage 5: animate
        render_dir = ku_dir / "render"
        render_results_path = render_dir / "render_results.json"
        if force_from <= stage_index("animate") or not render_results_path.exists():
            log(f"[5/6] animate: rendering {len(script.segments)} segment(s), quality={args.quality}")
            render_results = []
            for i, (seg, audio) in enumerate(zip(script.segments, segment_audios)):
                t0 = time.monotonic()
                result = render_segment(
                    seg, i, audio.duration_seconds, render_dir / f"seg_{i}",
                    quality=args.quality, manifest=manifest,
                )
                render_results.append(result)
                log(
                    f"    segment {i}: tier={result.tier} attempts={result.attempts} "
                    f"({time.monotonic() - t0:.1f}s)"
                )
            render_dir.mkdir(parents=True, exist_ok=True)
            render_results_path.write_text(
                RenderResultList(items=render_results).model_dump_json(indent=2)
            )
            run_dir.save_json(manifest_path, manifest)
        else:
            log(f"[5/6] animate: reusing existing renders for {ku.id}")
            render_results = RenderResultList.model_validate_json(
                render_results_path.read_text()
            ).items

        # Stage 6: assemble
        final_path = ku_dir / "final.mp4"
        if force_from <= stage_index("assemble") or not final_path.exists():
            log(f"[6/6] assemble: syncing + concatenating + captioning")
            diagnostics = assemble_ku_video(
                ku_dir, render_results, segment_audios,
                audio_dir / "narration.wav", audio_dir / "captions.srt",
            )
            (ku_dir / "assembly_diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
            log(f"    -> {diagnostics['final_path']} (max drift {diagnostics['max_abs_drift_seconds']:.2f}s)")
        else:
            log(f"[6/6] assemble: {ku.id} already has final.mp4")

    log(f"Done. Run directory: {run_dir.root}")
    log(f"Next: uv run python scripts/report.py --run {run_dir.root}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--syllabus", required=True, help="Path to the course syllabus (.pdf or .docx)")
    parser.add_argument("--slides", nargs="+", required=True, help="Path(s) to slide deck(s) (.pdf or .pptx)")
    parser.add_argument("--n-videos", type=int, default=3, help="How many top-ranked KUs to produce videos for")
    parser.add_argument("--ku-ids", nargs="+", default=None, help="Override selection with explicit KU ids")
    parser.add_argument("--out", default="runs/dev", help="Run output directory")
    parser.add_argument("--tts", default="kokoro", choices=["kokoro", "say", "elevenlabs"])
    parser.add_argument("--quality", default="low", choices=["low", "high"])
    parser.add_argument("--from-stage", default=None, choices=STAGES, help="Force recomputation from this stage onward")
    parser.add_argument("--skip-critic", action="store_true", help="Skip the semantic critique round (faster iteration)")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
