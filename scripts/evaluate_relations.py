#!/usr/bin/env python3
# Bu dosya, otomatik ilişki tahminlerini ayrı tutulan insan kontrollü beklentilere göre değerlendirmek için kullanılır.
"""Evaluate a relation prediction artifact against separate reviewed labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ykt_case.relation_evaluation import evaluate_relation_output


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate relation-matching output")
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--expectations", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    prediction = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
    expectations = json.loads(Path(args.expectations).read_text(encoding="utf-8"))
    result = evaluate_relation_output(prediction, expectations)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"status": result["status"], "output": str(output_path)}, indent=2))


if __name__ == "__main__":
    main()
