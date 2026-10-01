import unittest
from pathlib import Path
from tools.pdf_tool import handle_pdf_action
from main import run_pdf_tool


class TestPDFTool(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("tmp") / "test_pdf_tool"
        self.test_dir.mkdir(parents=True, exist_ok=True)

        self.txt_file = self.test_dir / "input.txt"
        self.txt_file.write_text("Testing PDF tool router and intent dispatcher.", encoding="utf-8")

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_handle_pdf_action_convert(self):
        pdf_out = self.test_dir / "output.pdf"
        res = handle_pdf_action("convert", {"input_file": str(self.txt_file), "target_format": "pdf", "output_path": str(pdf_out)})
        self.assertTrue(res["success"])
        self.assertTrue(Path(res["output_path"]).exists())

    def test_run_pdf_tool_wrapper(self):
        pdf_out = self.test_dir / "output_wrapper.pdf"
        res = run_pdf_tool("convert", {"input_file": str(self.txt_file), "target_format": "pdf", "output_path": str(pdf_out)}, started=0, warnings=[])
        self.assertIn("completed successfully", res["summary"])


if __name__ == "__main__":
    unittest.main()
