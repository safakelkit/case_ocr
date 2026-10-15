# Bu dosya, iki ilişki eşleme yönteminin aynı değerlendirme sözleşmesi altında karşılaştırılmasını test etmek için kullanılır.
import unittest

from ykt_case.relation_comparison import compare_relation_outputs


def prediction(method, selected, ranked):
    return {
        "method": {"name": method},
        "relations": [
            {
                "summary_row_id": "summary:row-1",
                "selected_note_row_ids": selected,
                "top_candidates": [
                    {"note_row_id": note_row_id} for note_row_id in ranked
                ],
                "confidence": 0.8,
            }
        ],
    }


class RelationComparisonTests(unittest.TestCase):
    def test_reports_metric_tie_but_changed_lower_ranking(self):
        expectations = {
            "examples": [
                {
                    "summary_row_id": "summary:row-1",
                    "required_note_row_ids": ["note:row-1"],
                }
            ]
        }
        result = compare_relation_outputs(
            prediction("baseline", ["note:row-1"], ["note:row-1", "note:row-2"]),
            prediction("semantic", ["note:row-1"], ["note:row-1", "note:row-3"]),
            expectations,
        )
        self.assertEqual(result["metrics"]["semantic_minus_baseline"]["mrr"], 0.0)
        self.assertEqual(result["agreement"]["same_selected_set"], 1)
        self.assertEqual(result["agreement"]["same_top1"], 1)
        self.assertEqual(result["agreement"]["same_top_k_order"], 0)


if __name__ == "__main__":
    unittest.main()
