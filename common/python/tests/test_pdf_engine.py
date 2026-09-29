import unittest
from pathlib import Path
from tools.pdf_converter import convert_txt_to_pdf, convert_images_to_pdf, convert_document
from tools.pdf_manipulator import merge_pdfs, split_pdf, rotate_pdf_pages, reorder_pdf_pages
from tools.pdf_extractor import extract_text_with_layout, extract_tables_from_pdf, ocr_scanned_pdf
from tools.pdf_security import add_watermark_to_pdf, add_page_numbers_to_pdf, redact_sensitive_data_in_pdf
from tools.pdf_tool import handle_pdf_action
from PIL import Image


class TestPDFEngineMaster(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("tmp") / "test_pdf_engine_master"
        self.test_dir.mkdir(parents=True, exist_ok=True)

        # Generate sample text and image files
        self.txt_file = self.test_dir / "sample.txt"
        self.txt_file.write_text("Master Test PDF Engine\nSSN: 000-11-2222\nPhone: 555-0199", encoding="utf-8")

        self.img_file = self.test_dir / "sample.png"
        Image.new("RGB", (150, 150), color="green").save(str(self.img_file))

        self.pdf1 = self.test_dir / "pdf1.pdf"
        convert_txt_to_pdf(self.txt_file, self.pdf1)

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_full_pipeline_conversions(self):
        # 1. TXT -> PDF
        pdf_out = self.test_dir / "txt_conv.pdf"
        res1 = convert_txt_to_pdf(self.txt_file, pdf_out)
        self.assertTrue(res1.exists())

        # 2. Images -> PDF
        img_pdf = self.test_dir / "img_conv.pdf"
        res2 = convert_images_to_pdf([self.img_file], img_pdf)
        self.assertTrue(res2.exists())

        # 3. Document Dispatcher
        res3 = convert_document(self.txt_file, "pdf")
        self.assertTrue(res3["success"])

    def test_full_pipeline_manipulation(self):
        merged = self.test_dir / "merged.pdf"
        res_merge = merge_pdfs([self.pdf1, self.pdf1], merged)
        self.assertTrue(res_merge.exists())

        rotated = self.test_dir / "rotated.pdf"
        res_rot = rotate_pdf_pages(self.pdf1, rotated, degrees=90)
        self.assertTrue(res_rot.exists())

    def test_full_pipeline_security_and_watermark(self):
        wm_pdf = self.test_dir / "wm.pdf"
        res_wm = add_watermark_to_pdf(self.pdf1, wm_pdf, watermark_text="CONFIDENTIAL")
        self.assertTrue(res_wm.exists())

        num_pdf = self.test_dir / "num.pdf"
        res_num = add_page_numbers_to_pdf(self.pdf1, num_pdf)
        self.assertTrue(res_num.exists())

        redact_pdf = self.test_dir / "redact.pdf"
        res_red = redact_sensitive_data_in_pdf(self.pdf1, redact_pdf)
        self.assertTrue(res_red.exists())

    def test_tool_dispatcher(self):
        out_pdf = self.test_dir / "tool_out.pdf"
        res = handle_pdf_action("convert", {"input_file": str(self.txt_file), "target_format": "pdf", "output_path": str(out_pdf)})
        self.assertTrue(res["success"])
        self.assertTrue(Path(res["output_path"]).exists())


if __name__ == "__main__":
    unittest.main()
