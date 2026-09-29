import unittest
from pathlib import Path
from tools.pdf_converter import convert_txt_to_pdf
from tools.pdf_manipulator import merge_pdfs, split_pdf, rotate_pdf_pages, reorder_pdf_pages


class TestPDFManipulator(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("tmp") / "test_pdf_manipulator"
        self.test_dir.mkdir(parents=True, exist_ok=True)

        # Create two sample PDF files for testing
        self.pdf1 = self.test_dir / "doc1.pdf"
        self.pdf2 = self.test_dir / "doc2.pdf"

        txt1 = self.test_dir / "txt1.txt"
        txt2 = self.test_dir / "txt2.txt"
        txt1.write_text("Document 1 Page 1 Content", encoding="utf-8")
        txt2.write_text("Document 2 Page 1 Content", encoding="utf-8")

        convert_txt_to_pdf(txt1, self.pdf1)
        convert_txt_to_pdf(txt2, self.pdf2)

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_merge_pdfs(self):
        merged_out = self.test_dir / "merged.pdf"
        res = merge_pdfs([self.pdf1, self.pdf2], merged_out)
        self.assertTrue(res.exists())
        self.assertGreater(res.stat().st_size, 0)

    def test_split_pdf(self):
        merged_out = self.test_dir / "merged.pdf"
        merge_pdfs([self.pdf1, self.pdf2], merged_out)

        split_dir = self.test_dir / "split"
        files = split_pdf(merged_out, split_dir)
        self.assertEqual(len(files), 2)
        self.assertTrue(files[0].exists())

    def test_rotate_pdf_pages(self):
        rotated_out = self.test_dir / "rotated.pdf"
        res = rotate_pdf_pages(self.pdf1, rotated_out, degrees=90)
        self.assertTrue(res.exists())

    def test_reorder_pdf_pages(self):
        merged_out = self.test_dir / "merged.pdf"
        merge_pdfs([self.pdf1, self.pdf2], merged_out)

        reordered_out = self.test_dir / "reordered.pdf"
        res = reorder_pdf_pages(merged_out, reordered_out, new_page_order=[2, 1])
        self.assertTrue(res.exists())


if __name__ == "__main__":
    unittest.main()
