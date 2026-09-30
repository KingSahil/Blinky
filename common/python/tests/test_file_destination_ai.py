import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from file_destination_ai import choose_destination, choose_destination_decision, drive_folders


class FileDestinationAITests(unittest.TestCase):
    def test_ai_selects_existing_folder_from_natural_language(self):
        folders = [r"C:\Users\Divam\Documents", r"C:\Users\Divam\Documents\Receipts"]
        with patch("file_destination_ai.ask_text_model", return_value={"folder_id": 1}) as model:
            self.assertEqual(choose_destination("put these where I keep receipts", folders), folders[1])
            self.assertIn("put these where I keep receipts", model.call_args.args[0])

    def test_ai_cannot_select_unlisted_folder(self):
        with patch("file_destination_ai.ask_text_model", return_value={"folder_id": 9000}):
            self.assertIsNone(choose_destination("put these in a missing folder", [r"C:\Users\Divam\Documents"]))

    def test_no_destination_in_prompt_uses_default(self):
        with patch("file_destination_ai.ask_text_model", return_value={"folder_id": None, "folder_requested": False}):
            self.assertEqual(
                choose_destination_decision("send this to my PC", [r"C:\Users\Divam\Documents"]),
                (None, False),
            )

    def test_c_drive_natural_language_lists_folders_at_drive_root(self):
        fake_folder = unittest.mock.Mock()
        fake_folder.path = r"C:\test"
        fake_folder.is_dir.return_value = True
        listing = unittest.mock.MagicMock()
        listing.__enter__.return_value = [fake_folder]
        with patch("file_destination_ai.os.scandir", return_value=listing) as scan:
            self.assertEqual(drive_folders("send this to the test folder in C drive"), [r"C:\test"])
            scan.assert_called_once_with("C:\\")

    def test_unnamed_drive_still_lists_system_drive_folders(self):
        fake_folder = unittest.mock.Mock()
        fake_folder.path = r"C:\test"
        fake_folder.is_dir.return_value = True
        listing = unittest.mock.MagicMock()
        listing.__enter__.return_value = [fake_folder]
        with patch("file_destination_ai.os.scandir", return_value=listing) as scan:
            with patch.dict("file_destination_ai.os.environ", {"SystemDrive": "C:"}):
                self.assertEqual(drive_folders("send this to the test folder"), [r"C:\test"])
            scan.assert_called_once_with("C:\\")

    def test_model_receives_home_relative_folder_labels(self):
        folder = str(Path.home() / "Documents" / "Receipts")
        with patch("file_destination_ai.ask_text_model", return_value={"folder_id": 0}) as model:
            self.assertEqual(choose_destination("send to Receipts", [folder]), folder)
            self.assertNotIn(str(Path.home()), model.call_args.args[0])
            self.assertIn("Home/Documents/Receipts", model.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
