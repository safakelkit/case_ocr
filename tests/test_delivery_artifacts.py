# Bu dosya, sabit teslim artefaktlarının ve kapsam-kanıt indeksinin eksiksiz üretildiğini test etmek için kullanılır.
import json
from pathlib import Path
import tempfile
import unittest

from scripts.prepare_delivery_artifacts import EVALUATION_FILES, prepare_delivery


class DeliveryArtifactsTests(unittest.TestCase):
    def test_copies_verified_reports_and_builds_requirement_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = root / "outputs"
            evaluations = root / "work" / "evaluation"
            outputs.mkdir(parents=True)
            evaluations.mkdir(parents=True)
            for name in ("result.json", "run_manifest.json"):
                (outputs / name).write_text("{}", encoding="utf-8")
            (outputs / "run_events.jsonl").write_text("{}\n", encoding="utf-8")
            for name in EVALUATION_FILES:
                (evaluations / name).write_text("{}", encoding="utf-8")

            index_path = prepare_delivery(root)
            index = json.loads(index_path.read_text(encoding="utf-8"))

            self.assertTrue((outputs / "evaluation" / EVALUATION_FILES[0]).is_file())
            self.assertEqual(
                index["runtime_artifacts"]["final_result"], "outputs/result.json"
            )
            self.assertEqual(len(index["artifact_inventory"]), 8)
            self.assertTrue(
                all(len(item["sha256"]) == 64 for item in index["artifact_inventory"])
            )
            self.assertGreaterEqual(len(index["requirement_evidence"]), 10)

    def test_fails_when_required_runtime_artifact_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                prepare_delivery(Path(directory))


if __name__ == "__main__":
    unittest.main()
