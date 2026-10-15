# Bu dosya, pipeline aşamalarını terminalden tek bir komutla çalıştırmak için kullanılır.
"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ykt_case.config import load_config
from ykt_case.orchestration import run_end_to_end
from ykt_case.progress import configure_progress
from ykt_case.pipeline import (
    run_baseline_matching,
    run_note_extraction,
    run_note_location,
    run_semantic_matching,
    run_summary_ocr,
    run_summary_structure,
    run_validation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the financial note-linking pipeline")
    parser.add_argument("--config", required=True, help="Path to a JSON configuration file")
    parser.add_argument(
        "--stage",
        choices=(
            "config",
            "summary-ocr",
            "summary-structure",
            "note-locate",
            "note-extract",
            "match-baseline",
            "match-semantic",
            "validate",
            "all",
        ),
        default="config",
        help="Pipeline stage to execute",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable terminal progress bars and status messages",
    )
    args = parser.parse_args()
    configure_progress(not args.no_progress)
    config = load_config(args.config)
    if args.stage == "all":
        output_path, manifest_path = run_end_to_end(config, Path(args.config))
        final_output = json.loads(output_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "status": final_output["status"],
                    "output": str(output_path),
                    "manifest": str(manifest_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if final_output["status"] == "failed":
            raise SystemExit(1)
        return
    if args.stage == "summary-ocr":
        output_path = run_summary_ocr(config)
        print(json.dumps({"status": "completed", "output": str(output_path)}, indent=2))
        return
    if args.stage == "summary-structure":
        output_path = run_summary_structure(config)
        stage_output = json.loads(output_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {"status": stage_output["status"], "output": str(output_path)},
                indent=2,
            )
        )
        return
    if args.stage == "note-locate":
        output_path = run_note_location(config)
        stage_output = json.loads(output_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {"status": stage_output["status"], "output": str(output_path)},
                indent=2,
            )
        )
        return
    if args.stage == "note-extract":
        output_path = run_note_extraction(config)
        stage_output = json.loads(output_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {"status": stage_output["status"], "output": str(output_path)},
                indent=2,
            )
        )
        return
    if args.stage == "match-baseline":
        output_path = run_baseline_matching(config)
        stage_output = json.loads(output_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {"status": stage_output["status"], "output": str(output_path)},
                indent=2,
            )
        )
        return
    if args.stage == "match-semantic":
        output_path = run_semantic_matching(config)
        stage_output = json.loads(output_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "status": stage_output["status"],
                    "fallback_used": stage_output["fallback_used"],
                    "output": str(output_path),
                },
                indent=2,
            )
        )
        return
    if args.stage == "validate":
        output_path = run_validation(config)
        stage_output = json.loads(output_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "status": stage_output["status"],
                    "validation_summary": stage_output["validation_summary"],
                    "output": str(output_path),
                },
                indent=2,
            )
        )
        if stage_output["status"] == "failed":
            raise SystemExit(1)
        return
    print(
        json.dumps(
            {
                "status": "configured",
                "source_pdf": str(config.source_pdf),
                "summary_pages": {
                    "start": config.summary_pages.start,
                    "end": config.summary_pages.end,
                },
                "target_notes": list(config.target_notes),
                "output_path": str(config.output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()