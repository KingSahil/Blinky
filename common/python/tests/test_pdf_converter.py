import unittest
from pathlib import Path
from tools.pdf_converter import convert_txt_to_pdf, convert_images_to_pdf, convert_document


class TestPDFConverter(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("tmp") / "test_pdf_converter"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_convert_txt_to_pdf(self):
        txt_file = self.test_dir / "sample.txt"
        txt_file.write_text("Hello Blinky PDF Engine!\nTesting conversion.", encoding="utf-8")

        pdf_out = self.test_dir / "sample.pdf"
        res = convert_txt_to_pdf(txt_file, pdf_out)
        self.assertTrue(res.exists())
        self.assertGreater(res.stat().st_size, 0)

    def test_convert_images_to_pdf(self):
        from PIL import Image

        img1 = self.test_dir / "img1.png"
        img2 = self.test_dir / "img2.png"
        Image.new("RGB", (100, 100), color="red").save(str(img1))
        Image.new("RGB", (100, 100), color="blue").save(str(img2))

        pdf_out = self.test_dir / "images_combined.pdf"
        res = convert_images_to_pdf([img1, img2], pdf_out)
        self.assertTrue(res.exists())
        self.assertGreater(res.stat().st_size, 0)

    def test_convert_document_dispatcher(self):
        txt_file = self.test_dir / "notes.md"
        txt_file.write_text("# Notes\n- Convert me to PDF", encoding="utf-8")

        res = convert_document(txt_file, "pdf")
        self.assertTrue(res["success"])
        self.assertTrue(Path(res["output_path"]).exists())


if __name__ == "__main__":
    unittest.main()
