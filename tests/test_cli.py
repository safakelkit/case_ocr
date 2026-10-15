# Bu dosya, terminal komutunun başarısız validasyonu işletim sistemine doğru çıkış koduyla bildirmesini test etmek için kullanılır.
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ykt_case.cli import main


class CliTests(unittest.TestCase):
    def test_validate_stage_exits_nonzero_when_validation_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "validation.json"
            output.write_text(
                json.dumps(
                    {"status": "failed", "validation_summary": {"failed": 1}}
                ),
                encoding="utf-8",
            )
            with (
                patch("sys.argv", ["ykt-case", "--config", "config.json", "--stage", "validate"]),
                patch("ykt_case.cli.load_config", return_value=object()),
                patch("ykt_case.cli.run_validation", return_value=output),
                patch("builtins.print"),
            ):
                with self.assertRaisesRegex(SystemExit, "1"):
                    main()


if __name__ == "__main__":
    unittest.main()
