# Bu dosya, yapılandırılmış PDF sayfa seçimi ve Poppler komutu oluşturma davranışlarını test etmek için kullanılır.
from pathlib import Path
import unittest

from ykt_case.config import PageRange
from ykt_case.rendering import build_render_command, select_configured_pages


class RenderingTests(unittest.TestCase):
    def test_command_uses_configured_one_based_page_range(self) -> None:
        command = build_render_command(
            executable="pdftoppm",
            source_pdf=Path("report.pdf"),
            output_prefix=Path("work/page"),
            pages=PageRange(5, 7),
            dpi=300,
        )
        self.assertEqual(command[1:5], ["-f", "5", "-l", "7"])
        self.assertIn("300", command)

    def test_stale_rendered_pages_do_not_break_current_range(self) -> None:
        rendered = [
            Path("summary-page-04.png"),
            Path("summary-page-05.png"),
            Path("summary-page-06.png"),
            Path("summary-page-07.png"),
            Path("summary-page-08.png"),
        ]
        selected = select_configured_pages(rendered, PageRange(5, 7))
        self.assertEqual(
            [path.name for path in selected],
            ["summary-page-05.png", "summary-page-06.png", "summary-page-07.png"],
        )
