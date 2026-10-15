# Bu dosya, dipnot başlığı bulma, devam sayfası birleştirme ve yanlış pozitifleri reddetme davranışlarını test etmek için kullanılır.
import unittest
import re

from ykt_case.note_locator import (
    HeadingCandidate,
    _normalize_title,
    extract_heading_candidates,
    locate_target_notes,
)
from ykt_case.schemas import BoundingBox, OcrToken, PageIdentity


def candidate(page, number, title, continuation=False, confidence=0.9):
    normalized = re.sub(r"\([^)]*devam[^)]*\)", "", title, flags=re.IGNORECASE)
    return HeadingCandidate(
        pdf_page_number=page,
        detected_number=number,
        raw_text=f"{number}. {title}",
        title=title,
        normalized_title=" ".join(normalized.casefold().split()),
        is_continuation=continuation,
        confidence=confidence,
        bbox={"left": 100, "top": 200, "width": 500, "height": 30},
    )


class NoteLocatorTests(unittest.TestCase):
    def test_short_continuation_heading_is_not_rejected_by_lowercase_suffix(self):
        page = PageIdentity(pdf_page_number=20, page_index=19)
        tokens = [
            OcrToken(
                text=text,
                bbox=BoundingBox(left=index * 70, top=100, width=60, height=20),
                confidence=0.95,
                page=page,
                block_number=1,
                paragraph_number=1,
                line_number=1,
                word_number=index + 1,
            )
            for index, text in enumerate(["10.", "STOKLAR", "(devamı)"])
        ]
        candidates = extract_heading_candidates(tokens)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].is_continuation)

    def test_turkish_dotless_i_title_normalization_is_consistent(self):
        self.assertEqual(_normalize_title("Yatırım"), _normalize_title("YATIRIM"))

    def test_arbitrary_exact_note_number_is_located(self):
        locations = locate_target_notes(
            [candidate(70, 30, "YATIRIM AMAÇLI GAYRİMENKULLER")],
            (30,),
        )
        self.assertEqual(locations[0]["note_number"], 30)
        self.assertEqual(locations[0]["pdf_pages"], [70])
        self.assertEqual(locations[0]["status"], "located")

    def test_corrupt_first_number_is_recovered_from_continuation(self):
        locations = locate_target_notes(
            [
                candidate(20, 1, "YATIRIM AMAÇLI GAYRİMENKULLER"),
                candidate(
                    21,
                    11,
                    "YATIRIM AMAÇLI GAYRİMENKULLER (devamı)",
                    continuation=True,
                ),
            ],
            (11,),
        )
        self.assertEqual(locations[0]["pdf_pages"], [20, 21])
        self.assertEqual(locations[0]["status"], "located_with_recovery")
        self.assertEqual(
            locations[0]["evidence"][-1]["kind"],
            "recovered_corrupt_heading_number",
        )

    def test_same_number_in_unrelated_table_row_is_not_added(self):
        locations = locate_target_notes(
            [
                candidate(
                    21,
                    11,
                    "YATIRIM AMAÇLI GAYRİMENKULLER (devamı)",
                    continuation=True,
                    confidence=0.92,
                ),
                candidate(
                    89,
                    11,
                    "UZUN VADELİ YÜKÜMLÜLÜKLER",
                    confidence=0.75,
                ),
            ],
            (11,),
        )
        self.assertEqual(locations[0]["pdf_pages"], [21])

    def test_missing_configured_note_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError, "note 30 was not found"):
            locate_target_notes([], (30,))
