import unittest
from pathlib import Path
from tools.pdf_converter import convert_txt_to_pdf
from tools.pdf_extractor import extract_text_with_layout, extract_tables_from_pdf, ocr_scanned_pdf


class TestPDFExtractor(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("tmp") / "test_pdf_extractor"
        self.test_dir.mkdir(parents=True, exist_ok=True)

        self.pdf_file = self.test_dir / "sample_layout.pdf"
        txt_file = self.test_dir / "sample.txt"
        txt_file.write_text("Column 1    Column 2    Column 3\nData A      Data B      Data C", encoding="utf-8")
        convert_txt_to_pdf(txt_file, self.pdf_file)

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_extract_text_with_layout(self):
        text = extract_text_with_layout(self.pdf_file)
        self.assertIn("Column 1", text)
        self.assertIn("Data A", text)

    def test_extract_tables_from_pdf(self):
        csv_out = self.test_dir / "extracted_tables.csv"
        tables = extract_tables_from_pdf(self.pdf_file, output_csv=csv_out)
        self.assertIsInstance(tables, list)

    def test_ocr_scanned_pdf(self):
        ocr_out = self.test_dir / "ocr_output.pdf"
        res = ocr_scanned_pdf(self.pdf_file, ocr_out)
        self.assertTrue(res.exists())


if __name__ == "__main__":
    unittest.main()
