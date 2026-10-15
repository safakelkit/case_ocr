#!/usr/bin/env python3
# Bu dosya, baseline ve anlamsal ilişki eşleme yöntemlerinin sonuçlarını karşılaştırmak için kullanılır.
"""Compare baseline and semantic outputs under one evaluation contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ykt_case.relation_comparison import compare_relation_outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--semantic", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare_relation_outputs(
        json.loads(args.baseline.read_text(encoding="utf-8")),
        json.loads(args.semantic.read_text(encoding="utf-8")),
        json.loads(args.expectations.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {"status": result["status"], "output": str(args.output)}, indent=2
        )
    )


if __name__ == "__main__":
    main()
