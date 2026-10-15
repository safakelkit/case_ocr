# Bu dosya, baseline ilişki aday üretme, sıralama, çoklu eşleme ve çekimser kalma davranışlarını test etmek için kullanılır.
import unittest

from ykt_case.matching import _lexical_similarity, match_relations_baseline


def summary_row(row_index, label, values, note_reference="30"):
    return {
        "row_index": row_index,
        "label": label,
        "note_reference": note_reference,
        "row_type": "detail",
        "confidence": 0.94,
        "source": {"pdf_page_number": 5},
        "cells": [
            {
                "role": "data_cell",
                "period": str(2024 - index),
                "raw_text": str(value),
                "normalized_value": value,
                "numeric_status": "value",
            }
            for index, value in enumerate(values)
        ],
    }


def note_row(row_index, label, values, row_type="detail"):
    return {
        "row_index": row_index,
        "label": label,
        "row_type": row_type,
        "confidence": 0.92,
        "source": {"pdf_page_number": 30},
        "cells": [
            {
                "role": "data_cell",
                "column_index": index + 1,
                "column_header": f"c{index + 1}",
                "raw_text": str(value),
                "normalized_value": value,
                "numeric_status": "value",
            }
            for index, value in enumerate(values)
        ],
    }


class MatchingTests(unittest.TestCase):
    def _note_output(self):
        return {
            "notes": [
                {
                    "note_number": 30,
                    "tables": [
                        {
                            "table_id": "note-30-p30-t1",
                            "page": {"pdf_page_number": 30},
                            "confidence": 0.90,
                            "rows": [
                                note_row(1, "Makul değer kazancı", [100]),
                                note_row(2, "Makul değer kazancı", [200]),
                                note_row(3, None, [300, 400], row_type="total"),
                                note_row(4, "İlgisiz satır", [999]),
                            ],
                        }
                    ],
                }
            ]
        }

    def test_selects_multiple_rows_to_cover_two_periods(self):
        summary_output = {
            "tables": [
                {
                    "table_id": "summary-p5",
                    "page": {"pdf_page_number": 5},
                    "rows": [summary_row(1, "Makul değer farkları", [100, 200])],
                }
            ]
        }
        result = match_relations_baseline(
            summary_output,
            self._note_output(),
            target_notes=(30,),
            top_k=4,
            minimum_candidate_score=0.35,
        )
        relation = result["relations"][0]
        self.assertEqual(relation["status"], "matched")
        self.assertEqual(relation["matched_value_coverage"], 1.0)
        self.assertEqual(
            set(relation["selected_note_row_ids"]),
            {"note-30-p30-t1:row-1", "note-30-p30-t1:row-2"},
        )

    def test_single_total_row_can_cover_both_periods(self):
        summary_output = {
            "tables": [
                {
                    "table_id": "summary-p5",
                    "page": {"pdf_page_number": 5},
                    "rows": [summary_row(2, "Yatırım amaçlı varlıklar", [300, 400])],
                }
            ]
        }
        result = match_relations_baseline(
            summary_output,
            self._note_output(),
            target_notes=(30,),
            top_k=3,
            minimum_candidate_score=0.35,
        )
        relation = result["relations"][0]
        self.assertEqual(
            relation["selected_note_row_ids"], ["note-30-p30-t1:row-3"]
        )
        self.assertEqual(len(relation["top_candidates"]), 3)

    def test_uses_emitted_note_row_id_instead_of_reconstructing_it(self):
        note_output = self._note_output()
        note_output["notes"][0]["tables"][0]["rows"][0]["row_id"] = "stable-row-id"
        summary_output = {
            "tables": [
                {
                    "table_id": "summary-p5",
                    "page": {"pdf_page_number": 5},
                    "rows": [summary_row(1, "Makul değer farkları", [100])],
                }
            ]
        }

        result = match_relations_baseline(
            summary_output,
            note_output,
            target_notes=(30,),
            top_k=4,
            minimum_candidate_score=0.35,
        )

        self.assertEqual(
            result["relations"][0]["selected_note_row_ids"], ["stable-row-id"]
        )

    def test_abstains_without_numeric_evidence(self):
        summary_output = {
            "tables": [
                {
                    "table_id": "summary-p5",
                    "page": {"pdf_page_number": 5},
                    "rows": [summary_row(3, "İlgisiz satır", [777, 888])],
                }
            ]
        }
        result = match_relations_baseline(
            summary_output,
            self._note_output(),
            target_notes=(30,),
            top_k=2,
            minimum_candidate_score=0.35,
        )
        relation = result["relations"][0]
        self.assertEqual(relation["status"], "abstained")
        self.assertEqual(relation["selected_note_row_ids"], [])
        self.assertEqual(relation["confidence"], 0.0)

    def test_one_note_cell_cannot_cover_two_equal_summary_periods(self):
        summary_output = {
            "tables": [
                {
                    "table_id": "summary-p5",
                    "page": {"pdf_page_number": 5},
                    "rows": [summary_row(4, "Tekrarlanan değer", [50, 50])],
                }
            ]
        }
        note_output = self._note_output()
        note_output["notes"][0]["tables"][0]["rows"] = [
            note_row(1, "Tek hücre", [50], row_type="total")
        ]
        result = match_relations_baseline(
            summary_output, note_output, (30,), top_k=2, minimum_candidate_score=0.35
        )
        relation = result["relations"][0]
        self.assertEqual(relation["matched_value_coverage"], 0.5)
        self.assertEqual(relation["status"], "partial_match")

    def test_multi_note_reference_keeps_configured_target(self):
        summary_output = {
            "tables": [
                {
                    "table_id": "summary-p5",
                    "page": {"pdf_page_number": 5},
                    "rows": [summary_row(5, "Çoklu referans", [100], "11, 30")],
                }
            ]
        }
        result = match_relations_baseline(
            summary_output, self._note_output(), (30,), top_k=2, minimum_candidate_score=0.35
        )
        self.assertEqual(len(result["relations"]), 1)
        self.assertEqual(result["relations"][0]["note_number"], 30)

    def test_turkish_dotless_i_normalizes_consistently(self):
        similarity = _lexical_similarity(
            "Yatırım Amaçlı Gayrimenkuller",
            "YATIRIM AMAÇLI GAYRİMENKULLER",
        )
        self.assertEqual(similarity["token_jaccard"], 1.0)
        self.assertEqual(similarity["combined"], 1.0)


if __name__ == "__main__":
    unittest.main()
