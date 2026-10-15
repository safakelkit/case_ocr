# Bu dosya, ilişki tahminleri için Top-1, Recall@k, MRR ve seçili-küme metriklerini hesaplamak için kullanılır.
"""Evaluation-only metrics for relation predictions and human-reviewed labels."""

from __future__ import annotations

import statistics
from typing import Any


def evaluate_relation_output(
    prediction: dict[str, Any], expectations: dict[str, Any]
) -> dict[str, Any]:
    relations = {
        relation["summary_row_id"]: relation
        for relation in prediction.get("relations", [])
    }
    examples: list[dict[str, Any]] = []
    for expected in expectations.get("examples", []):
        summary_row_id = expected["summary_row_id"]
        relation = relations.get(summary_row_id)
        if relation is None:
            examples.append(
                {
                    "summary_row_id": summary_row_id,
                    "found": False,
                    "selected_set_correct": False,
                    "top1_hit": False,
                    "recall_at_k": 0.0,
                    "reciprocal_rank": 0.0,
                }
            )
            continue
        relevant = set(
            expected.get("required_note_row_ids")
            or expected.get("acceptable_note_row_ids")
            or []
        )
        selected = set(relation.get("selected_note_row_ids", []))
        ranked = [
            candidate["note_row_id"]
            for candidate in relation.get("top_candidates", [])
        ]
        required = set(expected.get("required_note_row_ids", []))
        if required:
            selected_set_correct = selected == required
        else:
            selected_set_correct = bool(selected) and selected.issubset(relevant)
        relevant_ranks = [
            index + 1 for index, row_id in enumerate(ranked) if row_id in relevant
        ]
        examples.append(
            {
                "summary_row_id": summary_row_id,
                "found": True,
                "selected_set_correct": selected_set_correct,
                "top1_hit": bool(ranked) and ranked[0] in relevant,
                "recall_at_k": round(
                    len(relevant.intersection(ranked)) / len(relevant)
                    if relevant
                    else 0.0,
                    6,
                ),
                "reciprocal_rank": round(
                    1.0 / min(relevant_ranks) if relevant_ranks else 0.0,
                    6,
                ),
                "selected_note_row_ids": sorted(selected),
                "relevant_note_row_ids": sorted(relevant),
                "ranked_note_row_ids": ranked,
            }
        )
    if not examples:
        raise ValueError("relation expectations contain no examples")
    return {
        "stage": "relation_evaluation",
        "status": "completed",
        "method": prediction.get("method", {}).get("name"),
        "sample_size": len(examples),
        "metrics": {
            "selected_set_accuracy": round(
                statistics.fmean(example["selected_set_correct"] for example in examples),
                6,
            ),
            "top1_accuracy": round(
                statistics.fmean(example["top1_hit"] for example in examples), 6
            ),
            "mean_recall_at_k": round(
                statistics.fmean(example["recall_at_k"] for example in examples), 6
            ),
            "mrr": round(
                statistics.fmean(example["reciprocal_rank"] for example in examples),
                6,
            ),
        },
        "examples": examples,
        "limitations": [
            "Metrics are exploratory because the control set contains only the supplied case relationships.",
            "Acceptable alternatives are counted as relevant where repeated financial values make a unique row indefensible.",
        ],
    }
