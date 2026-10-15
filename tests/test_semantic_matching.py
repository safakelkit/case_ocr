# Bu dosya, embedding bağlamı, anlamsal sıralama, model kaydı ve açık fallback davranışını test etmek için kullanılır.
import unittest

from ykt_case.semantic_matching import (
    build_note_context,
    build_summary_context,
    match_relations_semantic,
    semantic_fallback_output,
)
from test_matching import note_row, summary_row


class FakeEncoder:
    def encode(self, texts):
        vectors = []
        for text in texts:
            text = text.casefold()
            if "değerleme farkları" in text or "değer değişikliğinden" in text:
                vectors.append([1.0, 0.0])
            elif "değerleme farkı" in text:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([0.5, 0.5])
        return vectors

    def metadata(self):
        return {"provider": "fake", "model_name": "test-model"}


class SemanticMatchingTests(unittest.TestCase):
    def test_semantic_signal_reranks_same_value_candidates(self):
        summary_output = {
            "tables": [
                {
                    "table_id": "summary-p5",
                    "page": {"pdf_page_number": 5},
                    "rows": [summary_row(1, "Değerleme farkları", [100])],
                }
            ]
        }
        note_output = {
            "notes": [
                {
                    "note_number": 30,
                    "tables": [
                        {
                            "table_id": "note-30-p30-t1",
                            "page": {"pdf_page_number": 30},
                            "confidence": 0.9,
                            "columns": [],
                            "rows": [
                                note_row(
                                    1,
                                    "Makul değer değişikliğinden kaynaklanan kazanç",
                                    [100],
                                ),
                                note_row(2, "Değerleme farkı", [100]),
                            ],
                        }
                    ],
                }
            ]
        }
        result = match_relations_semantic(
            summary_output,
            note_output,
            target_notes=(30,),
            top_k=2,
            minimum_candidate_score=0.35,
            encoder=FakeEncoder(),
        )
        relation = result["relations"][0]
        self.assertEqual(
            relation["top_candidates"][0]["note_row_id"],
            "note-30-p30-t1:row-1",
        )
        self.assertIn(
            "semantic_similarity", relation["top_candidates"][0]["features"]
        )

    def test_model_context_does_not_include_financial_values(self):
        summary = summary_row(1, "Yatırım amaçlı gayrimenkuller", [373992222])
        table = {"columns": [{"raw_text": "Toplam"}]}
        note = note_row(1, "Kapanış bakiyesi", [373992222], row_type="total")
        self.assertNotIn("373992222", build_summary_context(summary, 30))
        self.assertNotIn("373992222", build_note_context(table, note, 30))

    def test_note_context_prefers_normalized_header_but_preserves_raw_artifact(self):
        table = {
            "columns": [
                {
                    "raw_text": "31 Aralık 2012 Gerçeğe Uygun Ooo Değeri",
                    "normalized_text": "31 Aralık 2012 Gerçeğe Uygun Değeri",
                }
            ]
        }
        note = note_row(1, None, [100], row_type="total")

        context = build_note_context(table, note, 30)

        self.assertIn("Gerçeğe Uygun Değeri", context)
        self.assertNotIn("Ooo", context)

    def test_fallback_is_explicit_and_attributable(self):
        baseline = {
            "stage": "relation_matching_baseline",
            "status": "completed",
            "method": {"name": "baseline"},
            "relations": [
                {
                    "relation_id": "baseline:summary-p5:row-1:note-30",
                    "method": "baseline",
                }
            ],
        }
        result = semantic_fallback_output(
            baseline, "example/model", RuntimeError("offline")
        )
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["status"], "completed_with_warnings")
        self.assertIn("offline", result["fallback"]["reason"])
        self.assertEqual(result["fallback"]["original_result"]["status"], "failed")
        self.assertEqual(
            result["fallback"]["fallback_result"]["method"], {"name": "baseline"}
        )
        self.assertFalse(
            result["fallback"]["resulting_quality_change"][
                "semantic_evidence_available"
            ]
        )
        self.assertTrue(
            result["relations"][0]["relation_id"].startswith("semantic-fallback:")
        )


if __name__ == "__main__":
    unittest.main()
