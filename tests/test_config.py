# Bu dosya, yapılandırma yükleme ve doğrulama davranışlarını test etmek için kullanılır.
import json
from pathlib import Path
import tempfile
import unittest

from ykt_case.config import load_config


class ConfigTests(unittest.TestCase):
    def _write_config(self, payload: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "config.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_target_note_is_runtime_configuration(self) -> None:
        path = self._write_config(
            {
                "source_pdf": "report.pdf",
                "summary_pages": {"start": 5, "end": 7},
                "target_notes": [30],
                "output_path": "result.json",
                "ocr": {},
                "quality_gates": {
                    "period_header_coverage": {
                        "threshold": 1.0,
                        "action": "stop",
                        "rationale": "required test gate",
                    }
                },
            }
        )
        config = load_config(path)
        self.assertEqual(config.target_notes, (30,))
        self.assertEqual(config.ocr_engine, "tesseract")
        self.assertEqual(config.ocr_page_segmentation_mode, 3)
        self.assertEqual(config.note_search_render_dpi, 110)
        self.assertEqual(config.note_search_page_segmentation_mode, 6)
        self.assertEqual(config.note_extraction_render_dpi, 300)
        self.assertEqual(config.note_extraction_page_segmentation_mode, 3)
        self.assertEqual(config.matching_top_k, 5)
        self.assertEqual(config.matching_minimum_candidate_score, 0.35)
        self.assertEqual(
            config.semantic_model_name,
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        self.assertEqual(config.semantic_threads, 4)
        self.assertTrue(config.semantic_allow_download)
        self.assertEqual(config.quality_gates[0].name, "period_header_coverage")
        self.assertEqual(config.quality_gates[0].action, "stop")
        self.assertEqual(config.random_seed, 0)

    def test_rejects_zero_based_user_page(self) -> None:
        path = self._write_config(
            {
                "source_pdf": "report.pdf",
                "summary_pages": {"start": 0, "end": 7},
                "target_notes": [11],
                "output_path": "result.json",
                "ocr": {},
                "quality_gates": {
                    "test": {
                        "threshold": 1.0,
                        "rationale": "test gate",
                    }
                },
            }
        )
        with self.assertRaises(ValueError):
            load_config(path)

    def test_rejects_unsupported_ocr_engine(self) -> None:
        path = self._write_config(
            {
                "source_pdf": "report.pdf",
                "summary_pages": {"start": 5, "end": 7},
                "target_notes": [11],
                "output_path": "result.json",
                "ocr": {"engine": "unknown"},
                "quality_gates": {
                    "test": {
                        "threshold": 1.0,
                        "rationale": "test gate",
                    }
                },
            }
        )
        with self.assertRaisesRegex(ValueError, "only the tesseract"):
            load_config(path)
