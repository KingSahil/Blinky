import unittest
from pathlib import Path
from tools.pdf_converter import convert_txt_to_pdf
from tools.pdf_security import add_watermark_to_pdf, add_page_numbers_to_pdf, redact_sensitive_data_in_pdf


class TestPDFSecurity(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("tmp") / "test_pdf_security"
        self.test_dir.mkdir(parents=True, exist_ok=True)

        self.pdf_file = self.test_dir / "confidential_sample.pdf"
        txt_file = self.test_dir / "sample.txt"
        txt_file.write_text("Confidential Report\nSSN: 123-45-6789\nPhone: 555-0199", encoding="utf-8")
        convert_txt_to_pdf(txt_file, self.pdf_file)

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_add_watermark_to_pdf(self):
        wm_out = self.test_dir / "watermarked.pdf"
        res = add_watermark_to_pdf(self.pdf_file, wm_out, watermark_text="TOP SECRET")
        self.assertTrue(res.exists())
        self.assertGreater(res.stat().st_size, 0)

    def test_add_page_numbers_to_pdf(self):
        num_out = self.test_dir / "numbered.pdf"
        res = add_page_numbers_to_pdf(self.pdf_file, num_out)
        self.assertTrue(res.exists())

    def test_redact_sensitive_data_in_pdf(self):
        redact_out = self.test_dir / "redacted.pdf"
        res = redact_sensitive_data_in_pdf(self.pdf_file, redact_out)
        self.assertTrue(res.exists())


if __name__ == "__main__":
    unittest.main()
