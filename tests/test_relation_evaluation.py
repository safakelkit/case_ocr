# Bu dosya, ilişki değerlendirme metriklerinin insan kontrollü beklentiler üzerinde doğru hesaplanmasını test etmek için kullanılır.
import unittest

from ykt_case.relation_evaluation import evaluate_relation_output


class RelationEvaluationTests(unittest.TestCase):
    def test_supports_required_sets_and_acceptable_alternatives(self):
        prediction = {
            "method": {"name": "baseline"},
            "relations": [
                {
                    "summary_row_id": "s1",
                    "selected_note_row_ids": ["n2"],
                    "top_candidates": [
                        {"note_row_id": "n2"},
                        {"note_row_id": "n1"},
                    ],
                },
                {
                    "summary_row_id": "s2",
                    "selected_note_row_ids": ["n3", "n4"],
                    "top_candidates": [
                        {"note_row_id": "n3"},
                        {"note_row_id": "n4"},
                    ],
                },
            ],
        }
        expectations = {
            "examples": [
                {
                    "summary_row_id": "s1",
                    "acceptable_note_row_ids": ["n1", "n2"],
                },
                {
                    "summary_row_id": "s2",
                    "required_note_row_ids": ["n3", "n4"],
                },
            ]
        }
        result = evaluate_relation_output(prediction, expectations)
        self.assertEqual(result["metrics"]["selected_set_accuracy"], 1.0)
        self.assertEqual(result["metrics"]["top1_accuracy"], 1.0)
        self.assertEqual(result["metrics"]["mean_recall_at_k"], 1.0)
        self.assertEqual(result["metrics"]["mrr"], 1.0)

    def test_missing_prediction_is_counted_as_failure(self):
        result = evaluate_relation_output(
            {"method": {"name": "baseline"}, "relations": []},
            {"examples": [{"summary_row_id": "missing", "required_note_row_ids": ["n1"]}]},
        )
        self.assertEqual(result["metrics"]["selected_set_accuracy"], 0.0)
        self.assertFalse(result["examples"][0]["found"])


if __name__ == "__main__":
    unittest.main()
