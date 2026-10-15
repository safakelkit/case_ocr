# Bu dosya, ilişki sıralama yaklaşımlarını aynı insan kontrollü beklentiler ve metriklerle karşılaştırmak için kullanılır.
"""Compare relation-ranking approaches with the same reviewed expectations."""

from __future__ import annotations

from typing import Any

from ykt_case.relation_evaluation import evaluate_relation_output


def compare_relation_outputs(
    baseline: dict[str, Any],
    semantic: dict[str, Any],
    expectations: dict[str, Any],
) -> dict[str, Any]:
    baseline_evaluation = evaluate_relation_output(baseline, expectations)
    semantic_evaluation = evaluate_relation_output(semantic, expectations)
    baseline_by_id = {
        relation["summary_row_id"]: relation
        for relation in baseline.get("relations", [])
    }
    semantic_by_id = {
        relation["summary_row_id"]: relation
        for relation in semantic.get("relations", [])
    }
    evaluation_by_method = {
        "baseline": {
            item["summary_row_id"]: item
            for item in baseline_evaluation["examples"]
        },
        "semantic": {
            item["summary_row_id"]: item
            for item in semantic_evaluation["examples"]
        },
    }
    example_ids = sorted(set(baseline_by_id) | set(semantic_by_id))
    examples = []
    for summary_row_id in example_ids:
        baseline_relation = baseline_by_id.get(summary_row_id, {})
        semantic_relation = semantic_by_id.get(summary_row_id, {})
        baseline_ranked = [
            candidate["note_row_id"]
            for candidate in baseline_relation.get("top_candidates", [])
        ]
        semantic_ranked = [
            candidate["note_row_id"]
            for candidate in semantic_relation.get("top_candidates", [])
        ]
        baseline_selected = baseline_relation.get("selected_note_row_ids", [])
        semantic_selected = semantic_relation.get("selected_note_row_ids", [])
        examples.append(
            {
                "summary_row_id": summary_row_id,
                "selected_set_changed": set(baseline_selected)
                != set(semantic_selected),
                "top1_changed": (baseline_ranked[:1] != semantic_ranked[:1]),
                "ranking_changed": baseline_ranked != semantic_ranked,
                "baseline": {
                    "selected_note_row_ids": baseline_selected,
                    "ranked_note_row_ids": baseline_ranked,
                    "confidence": baseline_relation.get("confidence"),
                    "selected_set_correct": evaluation_by_method["baseline"]
                    .get(summary_row_id, {})
                    .get("selected_set_correct", False),
                },
                "semantic": {
                    "selected_note_row_ids": semantic_selected,
                    "ranked_note_row_ids": semantic_ranked,
                    "confidence": semantic_relation.get("confidence"),
                    "selected_set_correct": evaluation_by_method["semantic"]
                    .get(summary_row_id, {})
                    .get("selected_set_correct", False),
                },
            }
        )
    baseline_metrics = baseline_evaluation["metrics"]
    semantic_metrics = semantic_evaluation["metrics"]
    return {
        "stage": "relation_method_comparison",
        "status": "completed",
        "sample_size": len(example_ids),
        "metrics": {
            "baseline": baseline_metrics,
            "semantic": semantic_metrics,
            "semantic_minus_baseline": {
                name: round(semantic_metrics[name] - baseline_metrics[name], 6)
                for name in baseline_metrics
            },
        },
        "agreement": {
            "same_selected_set": sum(
                not item["selected_set_changed"] for item in examples
            ),
            "same_top1": sum(not item["top1_changed"] for item in examples),
            "same_top_k_order": sum(
                not item["ranking_changed"] for item in examples
            ),
        },
        "examples": examples,
        "interpretation_limit": (
            "The supplied case contains only two reviewed relationships; "
            "method differences are diagnostic and metrics are exploratory."
        ),
    }
