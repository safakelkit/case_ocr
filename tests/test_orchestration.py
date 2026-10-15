# Bu dosya, tek komutlu çalıştırma akışını, manifesti, fallback kaydını ve nihai çıktı üretimini test etmek için kullanılır.
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ykt_case.config import load_config
from ykt_case.orchestration import build_final_output, sha256_file


class OrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "report.pdf"
        self.source.write_bytes(b"scanned report")
        config_path = self.root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "source_pdf": str(self.source),
                    "summary_pages": {"start": 5, "end": 7},
                    "target_notes": [30],
                    "output_path": str(self.root / "result.json"),
                    "work_dir": str(self.root / "work"),
                    "ocr": {},
                    "quality_gates": {
                        "test_gate": {
                            "threshold": 1.0,
                            "rationale": "test-only gate",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.config = load_config(config_path)

    def test_sha256_file_is_content_based(self) -> None:
        self.assertEqual(
            sha256_file(self.source), hashlib.sha256(b"scanned report").hexdigest()
        )

    def test_final_output_uses_predictions_not_evaluation_labels(self) -> None:
        relation = {
            "relation_id": "relation-1",
            "summary_row_id": "summary-row-1",
            "status": "matched",
            "confidence": 0.61,
            "matched_value_coverage": 1.0,
            "ambiguous": False,
            "selected_note_row_ids": ["note-row-1"],
        }
        final_output = build_final_output(
            self.config,
            {
                "document_metadata": {"company": {"raw_text": "Test Bank"}},
                "tables": [],
            },
            {"notes": []},
            {"method": {"name": "baseline"}, "relations": [relation]},
            {
                "method": {"name": "semantic"},
                "fallback_used": False,
                "relations": [relation],
            },
            {
                "status": "completed_with_warnings",
                "validation_method_version": "1.0",
                "metrics": {},
                "quality_gates": [],
                "validation_summary": {},
                "validations": [],
                "limitations": [],
                "relation_confidences": [
                    {
                        "relation_id": "relation-1",
                        "final_confidence": 0.82,
                        "components": {},
                    }
                ],
            },
            Path("work/manifests/run-test.json"),
        )

        emitted = final_output["matching"]["relations"][0]
        self.assertEqual(emitted["matching_confidence"], 0.61)
        self.assertEqual(emitted["confidence"], 0.82)
        self.assertFalse(final_output["evaluation_labels_used_at_runtime"])
        self.assertNotIn("expectations", json.dumps(final_output))
        self.assertEqual(final_output["source"]["configured_target_notes"], [30])
        self.assertFalse(emitted["review_required"])
        self.assertEqual(emitted["quality_flags"], [])
        self.assertEqual(
            final_output["review_policy"]["threshold_source"],
            "configured_quality_gates",
        )

    def test_manifest_records_model_device_revision_and_quality_gates(self) -> None:
        from ykt_case.orchestration import run_end_to_end

        artifacts = self.root / "artifacts"
        artifacts.mkdir()

        def artifact(name: str, payload: dict) -> Path:
            path = artifacts / f"{name}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return path

        summary_ocr = artifact("summary_ocr", {"status": "completed"})
        summary = artifact(
            "summary",
            {"status": "completed", "document_metadata": {}, "tables": []},
        )
        note_location = artifact("note_location", {"status": "completed"})
        notes = artifact("notes", {"status": "completed", "notes": []})
        baseline = artifact(
            "baseline", {"status": "completed", "method": {"name": "baseline"}, "relations": []}
        )
        semantic = artifact(
            "semantic",
            {
                "status": "completed",
                "fallback_used": False,
                "method": {
                    "name": "semantic",
                    "model": {
                        "model_name": "example/model",
                        "source_revision": "revision-123",
                        "runtime": "onnxruntime_cpu",
                    },
                },
                "relations": [],
            },
        )
        validation = artifact(
            "validation",
            {
                "status": "completed_with_warnings",
                "validation_method_version": "1.0",
                "metrics": {},
                "quality_gates": [
                    {
                        "gate": "parse_rate",
                        "passed": False,
                        "outcome": "continue_with_warning",
                        "observed": 0.5,
                        "threshold": 0.8,
                    }
                ],
                "validation_summary": {"warning_gate_failures": 1},
                "validations": [],
                "limitations": [],
                "relation_confidences": [],
            },
        )
        config_path = self.root / "config.json"
        config_path.write_text("{}", encoding="utf-8")
        with (
            patch("ykt_case.orchestration.run_summary_ocr", return_value=summary_ocr),
            patch("ykt_case.orchestration.run_summary_structure", return_value=summary),
            patch("ykt_case.orchestration.run_note_location", return_value=note_location),
            patch("ykt_case.orchestration.run_note_extraction", return_value=notes),
            patch("ykt_case.orchestration.run_baseline_matching", return_value=baseline),
            patch("ykt_case.orchestration.run_semantic_matching", return_value=semantic),
            patch("ykt_case.orchestration.run_validation", return_value=validation),
        ):
            _, manifest_path = run_end_to_end(self.config, config_path)

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest_path, self.config.output_path.parent / "run_manifest.json")
        self.assertTrue((self.config.output_path.parent / "run_events.jsonl").exists())
        result = json.loads(self.config.output_path.read_text(encoding="utf-8"))
        self.assertEqual(result["run_manifest"], str(manifest_path))
        self.assertEqual(manifest["models"][0]["source_revision"], "revision-123")
        self.assertEqual(manifest["models"][0]["device"], "cpu")
        self.assertEqual(manifest["quality_gates"][0]["gate"], "parse_rate")
        self.assertEqual(manifest["validation_summary"]["warning_gate_failures"], 1)


if __name__ == "__main__":
    unittest.main()
