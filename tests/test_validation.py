# Bu dosya, kalite kapıları, yapısal-finansal kontroller ve nihai güven birleştirmesini test etmek için kullanılır.
import math
import unittest

from ykt_case.config import QualityGate
from ykt_case.validation import (
    aggregate_relation_confidence,
    evaluate_quality_gates,
    validate_financial,
    validate_format,
)


class ValidationTests(unittest.TestCase):
    def test_quality_gate_actions_are_explicit(self):
        gates = (
            QualityGate("minimum", 0.9, "gte", "continue_with_warning", "test"),
            QualityGate("maximum", 0.0, "lte", "stop", "test"),
        )
        results = evaluate_quality_gates(gates, {"minimum": 0.8, "maximum": 1.0})
        self.assertEqual(results[0]["outcome"], "continue_with_warning")
        self.assertEqual(results[1]["outcome"], "stop")

    def test_format_validation_rejects_non_finite_confidence(self):
        results = validate_format({"confidence": math.nan})
        confidence = next(item for item in results if item["check_id"] == "confidence_format")
        self.assertEqual(confidence["status"], "failed")

    def test_format_validation_accepts_bounded_percentage_range(self):
        results = validate_format(
            {
                "cells": [
                    {
                        "numeric_status": "percentage_range",
                        "normalized_value": {"min": 2.0, "max": 4.0},
                    }
                ]
            }
        )
        numeric = next(item for item in results if item["check_id"] == "numeric_representation")
        self.assertEqual(numeric["status"], "passed")

    def test_financial_detail_sum_reconciles_exactly(self):
        def cell(column, value, status="value"):
            return {
                "column_index": column,
                "normalized_value": value,
                "numeric_status": status,
            }

        note_output = {
            "notes": [
                {
                    "tables": [
                        {
                            "table_id": "note-30-t1",
                            "columns": [{"column_index": 1, "raw_text": "Toplam"}],
                            "rows": [
                                {"row_type": "detail", "cells": [cell(1, 100)]},
                                {"row_type": "detail", "cells": [cell(1, -20)]},
                                {"row_type": "total", "cells": [cell(1, 80)]},
                            ],
                        }
                    ]
                }
            ]
        }
        checks = validate_financial(note_output, {"relations": []})
        check = next(item for item in checks if "column-1" in item["check_id"])
        self.assertEqual(check["status"], "passed")
        self.assertEqual(check["evidence"]["difference"], 0.0)

    def test_financial_difference_is_a_failure(self):
        note_output = {
            "notes": [
                {
                    "tables": [
                        {
                            "table_id": "note-30-t1",
                            "columns": [{"column_index": 1, "raw_text": "Toplam"}],
                            "rows": [
                                {
                                    "row_type": "detail",
                                    "cells": [
                                        {
                                            "column_index": 1,
                                            "normalized_value": 100,
                                            "numeric_status": "value",
                                        }
                                    ],
                                },
                                {
                                    "row_type": "total",
                                    "cells": [
                                        {
                                            "column_index": 1,
                                            "normalized_value": 99,
                                            "numeric_status": "value",
                                        }
                                    ],
                                },
                            ],
                        }
                    ]
                }
            ]
        }
        checks = validate_financial(note_output, {"relations": []})
        check = next(item for item in checks if "column-1" in item["check_id"])
        self.assertEqual(check["status"], "failed")
        self.assertEqual(check["evidence"]["difference"], -1.0)

    def test_damaged_financial_cell_is_incomplete_not_guessed(self):
        note_output = {
            "notes": [
                {
                    "tables": [
                        {
                            "table_id": "note-30-t1",
                            "columns": [{"column_index": 1, "raw_text": "Toplam"}],
                            "rows": [
                                {
                                    "row_type": "detail",
                                    "cells": [
                                        {
                                            "column_index": 1,
                                            "normalized_value": None,
                                            "numeric_status": "invalid",
                                        }
                                    ],
                                },
                                {
                                    "row_type": "total",
                                    "cells": [
                                        {
                                            "column_index": 1,
                                            "normalized_value": 80,
                                            "numeric_status": "value",
                                        }
                                    ],
                                },
                            ],
                        }
                    ]
                }
            ]
        }
        checks = validate_financial(note_output, {"relations": []})
        check = next(item for item in checks if "column-1" in item["check_id"])
        self.assertEqual(check["status"], "incomplete")

    def test_final_confidence_uses_multiple_evidence_sources_and_ambiguity(self):
        relation_output = {
            "fallback_used": False,
            "relations": [
                {
                    "relation_id": "semantic:s1:n30",
                    "summary_row_id": "s1",
                    "note_number": 30,
                    "selected_note_row_ids": ["n1"],
                    "matched_value_coverage": 1.0,
                    "confidence": 0.8,
                    "ambiguous": True,
                    "status": "matched",
                    "top_candidates": [
                        {
                            "note_row_id": "n1",
                            "features": {"evidence_quality": 0.9},
                        }
                    ],
                }
            ],
        }
        baseline_output = {
            "relations": [
                {
                    "summary_row_id": "s1",
                    "note_number": 30,
                    "selected_note_row_ids": ["n1"],
                }
            ]
        }
        result = aggregate_relation_confidence(relation_output, baseline_output)[0]
        self.assertEqual(result["method"], "evidence_aggregated_confidence_v1")
        self.assertEqual(result["components"]["baseline_semantic_agreement"], 1.0)
        self.assertLess(result["final_confidence"], result["pre_penalty_confidence"])

    def test_abstention_does_not_gain_empty_set_agreement_confidence(self):
        relation_output = {
            "fallback_used": False,
            "relations": [
                {
                    "relation_id": "semantic:s1:n30",
                    "summary_row_id": "s1",
                    "note_number": 30,
                    "selected_note_row_ids": [],
                    "matched_value_coverage": 0.0,
                    "confidence": 0.0,
                    "ambiguous": False,
                    "status": "abstained",
                    "top_candidates": [],
                }
            ],
        }
        baseline_output = {
            "relations": [
                {
                    "summary_row_id": "s1",
                    "note_number": 30,
                    "selected_note_row_ids": [],
                }
            ]
        }
        result = aggregate_relation_confidence(relation_output, baseline_output)[0]
        self.assertEqual(result["components"]["baseline_semantic_agreement"], 0.0)
        self.assertEqual(result["final_confidence"], 0.0)

    def test_balance_sheet_totals_reconcile_by_period(self):
        def total_row(label, values):
            return {
                "label": label,
                "cells": [
                    {
                        "role": "data_cell",
                        "period": period,
                        "numeric_status": "value",
                        "normalized_value": value,
                    }
                    for period, value in values.items()
                ],
            }

        summary_output = {
            "tables": [
                {"rows": [total_row("TOPLAM VARLIKLAR", {"2012": 100, "2011": 80})]},
                {"rows": [total_row("TOPLAM KAYNAKLAR", {"2012": 100, "2011": 80})]},
            ]
        }
        checks = validate_financial({"notes": []}, {"relations": []}, summary_output)
        balance = next(
            item for item in checks if item["check_id"] == "balance_sheet_total_equality"
        )
        self.assertEqual(balance["status"], "passed")

    def test_unresolved_summary_aggregation_is_incomplete(self):
        summary_output = {
            "tables": [
                {
                    "rows": [
                        {
                            "row_id": "summary-p5:row-18",
                            "row_type": "total",
                            "aggregation_status": "unresolved",
                        }
                    ]
                }
            ]
        }
        checks = validate_financial({"notes": []}, {"relations": []}, summary_output)
        aggregation = next(
            item
            for item in checks
            if item["check_id"] == "summary_aggregation_reconciliation"
        )
        self.assertEqual(aggregation["status"], "incomplete")
        self.assertEqual(
            aggregation["evidence"]["unresolved_row_ids"],
            ["summary-p5:row-18"],
        )

    def test_evidence_resolved_normalization_keeps_parser_provenance(self):
        summary_output = {
            "tables": [
                {
                    "rows": [
                        {
                            "row_id": "summary-p5:row-13",
                            "cells": [
                                {
                                    "period": "2012",
                                    "raw_text": "4,224",
                                    "normalized_value": 4224,
                                    "normalization_ambiguity": (
                                        "decimal_or_thousands_separator"
                                    ),
                                    "normalization_resolution": {
                                        "method": (
                                            "parent_child_financial_reconciliation"
                                        ),
                                        "parser_normalized_value": 4.224,
                                        "selected_normalized_value": 4224,
                                        "target_row_id": "summary-p5:row-10",
                                    },
                                }
                            ],
                        }
                    ]
                }
            ]
        }
        checks = validate_financial({"notes": []}, {"relations": []}, summary_output)
        provenance = next(
            item
            for item in checks
            if item["check_id"] == "summary_normalization_provenance"
        )
        self.assertEqual(provenance["status"], "passed")
        correction = provenance["evidence"]["evidence_resolved_corrections"][0]
        self.assertEqual(correction["parser_normalized_value"], 4.224)
        self.assertEqual(correction["selected_normalized_value"], 4224)


if __name__ == "__main__":
    unittest.main()
