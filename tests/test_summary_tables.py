# Bu dosya, özet tablo çıkarımı ile kanıta dayalı ebeveyn-çocuk ve toplam ilişkilerini test etmek için kullanılır.
import unittest

from ykt_case.summary_tables import _assign_row_relationships, extract_summary_page


def token(text, left, top, width, line, confidence=0.95):
    return {
        "text": text,
        "bbox": {"left": left, "top": top, "width": width, "height": 20},
        "confidence": confidence,
        "page": {"pdf_page_number": 9, "page_index": 8, "printed_page_number": None},
        "block_number": line,
        "paragraph_number": 1,
        "line_number": 1,
        "word_number": 1,
    }


class SummaryTableTests(unittest.TestCase):
    def test_detects_dynamic_period_columns_and_arbitrary_note_reference(self):
        page = {
            "pdf_page_number": 9,
            "tokens": [
                token("ÖRNEK", 100, 30, 80, 1),
                token("ŞİRKET", 190, 30, 80, 1),
                token("KONSOLİDE", 100, 60, 110, 2),
                token("BİLANÇO", 220, 60, 90, 2),
                token("(TL)", 100, 90, 40, 3),
                token("Referansları", 500, 120, 110, 4),
                token("2024", 720, 120, 60, 5),
                token("2023", 940, 120, 60, 5),
                token("Yatırım", 100, 180, 80, 6),
                token("Amaçlı", 190, 180, 70, 6),
                token("Varlıklar", 270, 180, 90, 6),
                token("30", 530, 182, 30, 7),
                token("1.234.567", 700, 182, 100, 7),
                token("(765.432)", 920, 182, 105, 7),
                token("1", 550, 500, 10, 8),
            ],
        }

        table = extract_summary_page(page)

        self.assertEqual([period["raw_text"] for period in table["periods"]], ["2024", "2023"])
        self.assertEqual(
            [column["role"] for column in table["columns"]],
            ["row_header", "note_reference", "data_column", "data_column"],
        )
        self.assertEqual(
            [
                column.get("period")
                for column in table["columns"]
                if column["role"] == "data_column"
            ],
            ["2024", "2023"],
        )
        financial_row = next(row for row in table["rows"] if row["note_reference"] == "30")
        self.assertEqual(financial_row["label"], "Yatırım Amaçlı Varlıklar")
        values = [cell for cell in financial_row["cells"] if cell["role"] == "data_cell"]
        self.assertEqual([cell["normalized_value"] for cell in values], [1234567, -765432])
        self.assertEqual(table["page"]["pdf_page_number"], 9)
        self.assertEqual(table["page"]["page_index"], 8)
        self.assertEqual(table["page"]["printed_page_number"], 1)
        self.assertEqual(financial_row["row_id"], "summary-p9:row-1")
        self.assertEqual(financial_row["aggregation_status"], "not_applicable")

    def test_combines_adjacent_multiline_statement_title(self):
        page = {
            "pdf_page_number": 9,
            "tokens": [
                token("ÖRNEK", 100, 20, 80, 1),
                token("ŞİRKET", 190, 20, 80, 1),
                token("BAĞIMSIZ", 100, 70, 90, 2),
                token("DENETİMDEN", 200, 70, 110, 2),
                token("GEÇMİŞ", 320, 70, 80, 2),
                token("31", 410, 70, 25, 2),
                token("ARALIK", 445, 70, 70, 2),
                token("2012", 525, 70, 50, 2),
                token("TARİHLİ", 585, 70, 75, 2),
                token("KONSOLİDE", 100, 105, 110, 3),
                token("BİLANÇO", 220, 105, 90, 3),
                token("(TL)", 100, 140, 40, 4),
                token("Referansları", 500, 170, 110, 5),
                token("2024", 720, 170, 60, 6),
                token("2023", 940, 170, 60, 6),
                token("Kalem", 100, 230, 70, 7),
                token("30", 530, 232, 30, 8),
                token("100", 720, 232, 50, 8),
                token("90", 940, 232, 40, 8),
            ],
        }

        table = extract_summary_page(page)

        self.assertEqual(
            table["title"],
            "BAĞIMSIZ DENETİMDEN GEÇMİŞ 31 ARALIK 2012 TARİHLİ KONSOLİDE BİLANÇO",
        )

    def test_emits_parent_child_and_reconciled_total_relations(self):
        page = {
            "pdf_page_number": 9,
            "tokens": [
                token("ÖRNEK", 100, 30, 80, 1),
                token("KONSOLİDE", 100, 60, 110, 2),
                token("BİLANÇO", 220, 60, 90, 2),
                token("(TL)", 100, 90, 40, 3),
                token("Referansları", 500, 120, 110, 4),
                token("2024", 720, 120, 60, 5),
                token("2023", 940, 120, 60, 5),
                token("Varlıklar", 100, 150, 100, 6),
                token("Nakit", 130, 230, 70, 7),
                token("100", 720, 230, 50, 8),
                token("80", 940, 230, 40, 8),
                token("Alacaklar", 130, 290, 100, 9),
                token("50", 720, 290, 40, 10),
                token("40", 940, 290, 40, 10),
                token("TOPLAM", 100, 350, 90, 11),
                token("150", 720, 350, 50, 12),
                token("120", 940, 350, 50, 12),
            ],
        }

        table = extract_summary_page(page)
        section, first, second, total = table["rows"]
        self.assertEqual(section["hierarchy_role"], "section")
        self.assertEqual(first["parent_row_id"], section["row_id"])
        self.assertEqual(second["parent_row_id"], section["row_id"])
        self.assertEqual(section["child_row_ids"], [first["row_id"], second["row_id"], total["row_id"]])
        self.assertEqual(total["aggregation_status"], "reconciled")
        self.assertEqual(
            total["aggregation_of_row_ids"], [first["row_id"], second["row_id"]]
        )
        self.assertIn(total["row_id"], first["aggregated_by_row_ids"])

    def test_missing_period_headers_fails_explicitly(self):
        page = {
            "pdf_page_number": 9,
            "tokens": [token("KONSOLİDE", 100, 60, 110, 1)],
        }
        with self.assertRaisesRegex(ValueError, "period headers"):
            extract_summary_page(page)

    def test_unlabeled_row_stops_section_membership_inference(self):
        rows = [
            {"row_type": "section_header", "label": "Dağılım", "bbox": {"left": 100}, "cells": []},
            {"row_type": "detail", "label": "Pay A", "bbox": {"left": 100}, "cells": []},
            {"row_type": "detail", "label": None, "bbox": {"left": 500}, "cells": []},
            {"row_type": "detail", "label": "Yeni kalem", "bbox": {"left": 100}, "cells": []},
        ]

        _assign_row_relationships("summary-p9", rows)

        self.assertEqual(rows[1]["parent_row_id"], rows[0]["row_id"])
        self.assertIsNone(rows[2]["parent_row_id"])
        self.assertIsNone(rows[3]["parent_row_id"])

    def test_unlabeled_exact_sum_is_parentless_reconciled_total(self):
        def cells(first, second):
            return [
                {
                    "role": "data_cell",
                    "period": "2012",
                    "normalized_value": first,
                    "numeric_status": "value",
                },
                {
                    "role": "data_cell",
                    "period": "2011",
                    "normalized_value": second,
                    "numeric_status": "value",
                },
            ]

        rows = [
            {
                "row_type": "section_header",
                "label": "Dağılım",
                "bbox": {"left": 100},
                "cells": [],
            },
            {
                "row_type": "detail",
                "label": "Pay A",
                "bbox": {"left": 130},
                "cells": cells(40, 30),
            },
            {
                "row_type": "detail",
                "label": "Pay B",
                "bbox": {"left": 130},
                "cells": cells(60, 70),
            },
            {
                "row_type": "detail",
                "label": None,
                "bbox": {"left": 700},
                "cells": cells(100, 100),
            },
        ]

        _assign_row_relationships("summary-p9", rows)

        total = rows[3]
        self.assertEqual(total["row_type"], "total")
        self.assertEqual(total["hierarchy_role"], "total")
        self.assertIsNone(total["parent_row_id"])
        self.assertEqual(total["hierarchy_basis"], "financial_reconciliation")
        self.assertEqual(total["aggregation_status"], "reconciled")
        self.assertEqual(
            total["aggregation_of_row_ids"],
            [rows[1]["row_id"], rows[2]["row_id"]],
        )
        self.assertNotIn(total["row_id"], rows[0]["child_row_ids"])

    def test_missing_note_reference_header_fails_explicitly(self):
        page = {
            "pdf_page_number": 9,
            "tokens": [
                token("KONSOLİDE", 100, 60, 110, 1),
                token("2024", 720, 120, 60, 2),
                token("2023", 940, 120, 60, 2),
                token("Satışlar", 100, 180, 80, 3),
                token("1.000", 700, 182, 80, 4),
                token("900", 940, 182, 60, 4),
            ],
        }
        with self.assertRaisesRegex(ValueError, "note-reference column"):
            extract_summary_page(page)
