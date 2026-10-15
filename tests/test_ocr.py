# Bu dosya, Tesseract TSV çıktısının metin, koordinat ve güven kayıtlarına dönüştürülmesini test etmek için kullanılır.
import unittest

from ykt_case.ocr import parse_tesseract_tsv


TSV = """level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext
1\t1\t0\t0\t0\t0\t0\t0\t100\t100\t-1\t
5\t1\t1\t1\t1\t1\t10\t20\t30\t12\t96.500000\tYatırım
5\t1\t1\t1\t1\t2\t45\t20\t40\t12\t88.000000\tAmaçlı
"""


class OcrTests(unittest.TestCase):
    def test_parses_word_level_tokens_with_page_provenance(self) -> None:
        tokens = parse_tesseract_tsv(TSV, pdf_page_number=5)
        self.assertEqual([token.text for token in tokens], ["Yatırım", "Amaçlı"])
        self.assertEqual(tokens[0].page.pdf_page_number, 5)
        self.assertEqual(tokens[0].page.page_index, 4)
        self.assertEqual(tokens[0].confidence, 0.965)
        self.assertEqual(tokens[0].bbox.left, 10)
