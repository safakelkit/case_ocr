# Bu dosya, ortak şema kurallarını, sayfa kimliğini ve güven aralığı doğrulamasını test etmek için kullanılır.
import math
import unittest

from ykt_case.schemas import PageIdentity, validate_confidence


class SchemaTests(unittest.TestCase):
    def test_page_identity_distinguishes_pdf_and_printed_numbers(self) -> None:
        page = PageIdentity(pdf_page_number=53, page_index=52, printed_page_number=49)
        self.assertEqual(page.printed_page_number, 49)

    def test_confidence_accepts_boundaries(self) -> None:
        self.assertEqual(validate_confidence(0.0), 0.0)
        self.assertEqual(validate_confidence(1.0), 1.0)

    def test_confidence_rejects_non_finite_and_out_of_range(self) -> None:
        for value in (-0.01, 1.01, math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_confidence(value)
