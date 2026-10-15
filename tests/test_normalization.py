# Bu dosya, finansal sayı normalizasyonunun nokta, parantez, tire, boşluk ve sıfır ayrımlarını test etmek için kullanılır.
import unittest

from ykt_case.normalization import NumericStatus, parse_financial_number


class FinancialNumberTests(unittest.TestCase):
    def test_thousands_separator(self) -> None:
        parsed = parse_financial_number("373.992.222")
        self.assertEqual((parsed.value, parsed.status), (373992222, NumericStatus.VALUE))

    def test_decimal_comma(self) -> None:
        parsed = parse_financial_number("0,058")
        self.assertEqual(parsed.value, 0.058)
        self.assertEqual(parsed.status, NumericStatus.VALUE)

    def test_parentheses_mean_negative(self) -> None:
        parsed = parse_financial_number("(49.167.330)")
        self.assertEqual((parsed.value, parsed.status), (-49167330, NumericStatus.VALUE))

    def test_dash_blank_and_zero_are_distinct(self) -> None:
        self.assertEqual(parse_financial_number("-").status, NumericStatus.DASH)
        self.assertEqual(parse_financial_number("").status, NumericStatus.BLANK)
        zero = parse_financial_number("0")
        self.assertEqual((zero.value, zero.status), (0, NumericStatus.VALUE))

    def test_invalid_value_preserves_raw_text(self) -> None:
        parsed = parse_financial_number("12.34")
        self.assertEqual(parsed.raw, "12.34")
        self.assertEqual(parsed.status, NumericStatus.INVALID)
