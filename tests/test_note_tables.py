# Bu dosya, dipnot tablolarının geometrik satır, sütun, hücre ve uyarı çıkarımını test etmek için kullanılır.
import unittest

from ykt_case.note_tables import (
    _cell_value,
    _reconcile_unlabeled_totals,
    extract_note_document,
    extract_note_page,
)


def token(text, left, top, width, line, confidence=0.95, page_number=30):
    return {
        "text": text,
        "bbox": {"left": left, "top": top, "width": width, "height": 20},
        "confidence": confidence,
        "page": {
            "pdf_page_number": page_number,
            "page_index": page_number - 1,
            "printed_page_number": None,
        },
        "block_number": line,
        "paragraph_number": 1,
        "line_number": 1,
        "word_number": 1,
    }


def synthetic_page():
    return {
        "pdf_page_number": 30,
        "tokens": [
            token("31", 680, 65, 25, 1),
            token("31", 880, 65, 25, 1),
            token("2024", 675, 100, 50, 1),
            token("2023", 875, 100, 50, 1),
            token("Doluluk", 100, 180, 80, 2),
            token("oranı", 190, 180, 50, 2),
            token("(%)", 250, 180, 35, 2),
            token("%86,6", 675, 180, 55, 2),
            token("%80,8", 875, 180, 55, 2),
            token("Kira", 100, 225, 40, 3),
            token("artış", 150, 225, 45, 3),
            token("oranı", 205, 225, 50, 3),
            token("(%)", 265, 225, 35, 3),
            token("%3", 680, 225, 35, 3),
            token("4-6", 875, 225, 45, 3, confidence=0.60),
            token("Arazi", 625, 500, 70, 4),
            token("Ooo", 700, 500, 35, 4, confidence=0.40),
            token("Bina", 830, 500, 55, 4),
            token("1", 100, 545, 10, 5),
            token("Ocak", 120, 545, 40, 5),
            token("2024", 170, 545, 45, 5),
            token("açılış", 225, 545, 55, 5),
            token("bakiyesi", 290, 545, 65, 5),
            token("(Düzenlenmiş)", 100, 580, 110, 5),
            token("100", 650, 580, 45, 5),
            token("200", 850, 580, 45, 5),
            token("Kapanış", 100, 625, 75, 6),
            token("(50)", 650, 625, 45, 6),
            token("-", 865, 625, 15, 6),
            token("26", 530, 950, 25, 7),
            token("footer", 1050, 950, 50, 8),
        ],
    }


class NoteTableTests(unittest.TestCase):
    def test_wide_table_columns_are_detected_left_of_old_right_side_cutoff(self):
        page = synthetic_page()
        for item in page["tokens"]:
            left = item["bbox"]["left"]
            if 600 <= left < 1000:
                item["bbox"]["left"] = left - 300

        tables = extract_note_page(page, note_number=30)

        self.assertEqual(len(tables), 2)
        self.assertEqual(len(tables[0]["columns"]), 2)
        self.assertLess(tables[0]["columns"][0]["anchor_x"], 1100 * 0.46)

    def test_detects_multiple_tables_and_preserves_value_types(self):
        tables = extract_note_page(synthetic_page(), note_number=30)

        self.assertEqual(len(tables), 2)
        ratio_table, value_table = tables
        self.assertEqual(ratio_table["note_number"], 30)
        self.assertEqual(
            [column["raw_text"] for column in ratio_table["columns"]],
            ["31 2024", "31 2023"],
        )
        occupancy = ratio_table["rows"][0]
        self.assertEqual(occupancy["label"], "Doluluk oranı (%)")
        self.assertEqual(
            [cell["normalized_value"] for cell in occupancy["cells"]],
            [86.6, 80.8],
        )
        self.assertEqual(occupancy["cells"][0]["numeric_status"], "percentage")
        rent_range = ratio_table["rows"][1]["cells"][1]
        self.assertEqual(rent_range["numeric_status"], "invalid")
        self.assertIsNone(rent_range["normalized_value"])
        self.assertEqual(
            _cell_value("%2-%4", "İskonto oranı"),
            ({"min": 2.0, "max": 4.0}, "percentage_range"),
        )
        self.assertEqual(_cell_value("%10", "Faiz oranı"), (10.0, "percentage"))
        self.assertEqual(_cell_value("", "Faiz oranı (%)"), (None, "blank"))
        closing = value_table["rows"][1]
        self.assertEqual(
            [column["column_id"] for column in value_table["columns"]],
            ["note-30-p30-t2:column-1", "note-30-p30-t2:column-2"],
        )
        self.assertEqual(value_table["columns"][0]["raw_text"], "Arazi Ooo")
        self.assertEqual(value_table["columns"][0]["normalized_text"], "Arazi")
        self.assertTrue(
            any(
                warning["code"] == "column_header_ocr_noise_removed"
                for warning in value_table["warnings"]
            )
        )
        self.assertEqual(
            value_table["rows"][0]["label"],
            "1 Ocak 2024 açılış bakiyesi (Düzenlenmiş)",
        )
        self.assertEqual(
            value_table["rows"][0]["row_id"], "note-30-p30-t2:row-1"
        )
        self.assertEqual(
            value_table["rows"][0]["cells"][0]["column_id"],
            "note-30-p30-t2:column-1",
        )
        self.assertEqual(
            value_table["rows"][0]["cells"][0]["column_header"], "Arazi"
        )
        self.assertEqual(
            value_table["rows"][0]["cells"][0]["column_header_raw"],
            "Arazi Ooo",
        )
        self.assertEqual(
            [cell["normalized_value"] for cell in closing["cells"]],
            [-50, None],
        )
        self.assertEqual(closing["cells"][1]["numeric_status"], "dash")
        self.assertEqual(value_table["page"]["pdf_page_number"], 30)
        self.assertEqual(value_table["page"]["page_index"], 29)
        self.assertEqual(value_table["page"]["printed_page_number"], 26)

    def test_document_uses_runtime_note_location(self):
        page = synthetic_page()
        result = extract_note_document(
            {"pages": [page]},
            [
                {
                    "note_number": 30,
                    "title": "ÖRNEK NOT",
                    "pdf_pages": [30],
                    "confidence": 0.91,
                }
            ],
        )

        self.assertEqual(result["notes"][0]["note_number"], 30)
        self.assertEqual(result["notes"][0]["pdf_pages"], [30])
        self.assertEqual(result["status"], "completed_with_warnings")

    def test_missing_note_tables_fails_explicitly(self):
        page = {"pdf_page_number": 30, "tokens": [token("metin", 100, 100, 50, 1)]}
        with self.assertRaisesRegex(ValueError, "no tables"):
            extract_note_document(
                {"pages": [page]},
                [
                    {
                        "note_number": 30,
                        "title": "ÖRNEK",
                        "pdf_pages": [30],
                        "confidence": 0.9,
                    }
                ],
            )

    def test_unlabeled_row_requires_exact_reconciliation_to_be_total(self):
        rows = [
            {
                "row_id": "r1",
                "label": "A",
                "row_type": "detail",
                "cells": [{"column_index": 1, "numeric_status": "value", "normalized_value": 40}],
            },
            {
                "row_id": "r2",
                "label": "B",
                "row_type": "detail",
                "cells": [{"column_index": 1, "numeric_status": "value", "normalized_value": 60}],
            },
            {
                "row_id": "r3",
                "label": None,
                "row_type": "unresolved",
                "classification_basis": "missing_label",
                "aggregation_of_row_ids": [],
                "cells": [{"column_index": 1, "numeric_status": "value", "normalized_value": 100}],
            },
        ]
        _reconcile_unlabeled_totals(rows)
        self.assertEqual(rows[2]["row_type"], "total")
        self.assertEqual(rows[2]["classification_basis"], "financial_reconciliation")
        self.assertEqual(rows[2]["aggregation_of_row_ids"], ["r1", "r2"])

        rows[2]["cells"][0]["normalized_value"] = 99
        rows[2]["row_type"] = "unresolved"
        rows[2]["classification_basis"] = "missing_label"
        rows[2]["aggregation_of_row_ids"] = []
        _reconcile_unlabeled_totals(rows)
        self.assertEqual(rows[2]["row_type"], "unresolved")


if __name__ == "__main__":
    unittest.main()
