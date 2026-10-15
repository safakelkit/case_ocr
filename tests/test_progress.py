# Bu dosya, terminal ilerlemesinin ölçülebilir işleri koruduğunu ve gerektiğinde tamamen kapatılabildiğini test etmek için kullanılır.
import unittest
from unittest.mock import patch

from ykt_case.progress import configure_progress, progress_message, track


class ProgressTests(unittest.TestCase):
    def tearDown(self) -> None:
        configure_progress(False)

    def test_disabled_progress_preserves_iterable(self) -> None:
        configure_progress(False)
        with patch("ykt_case.progress.tqdm") as mocked_tqdm:
            mocked_tqdm.return_value = iter([1, 2, 3])
            self.assertEqual(
                list(track([1, 2, 3], description="Test", total=3)),
                [1, 2, 3],
            )
        self.assertTrue(mocked_tqdm.call_args.kwargs["disable"])

    def test_enabled_progress_is_not_disabled(self) -> None:
        configure_progress(True)
        with patch("ykt_case.progress.tqdm") as mocked_tqdm:
            mocked_tqdm.return_value = iter([1])
            list(track([1], description="Test", total=1))
        self.assertFalse(mocked_tqdm.call_args.kwargs["disable"])

    def test_status_message_respects_progress_setting(self) -> None:
        with patch("ykt_case.progress.tqdm.write") as mocked_write:
            configure_progress(False)
            progress_message("gizli")
            configure_progress(True)
            progress_message("görünür")
        mocked_write.assert_called_once_with("görünür")


if __name__ == "__main__":
    unittest.main()
