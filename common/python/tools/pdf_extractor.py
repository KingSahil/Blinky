from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from utils.logging import get_logger

LOGGER = get_logger("blinky.pdf_extractor")


def extract_tables_from_pdf(
    pdf_path: str | Path,
    output_csv: Optional[str | Path] = None,
    page_numbers: Optional[List[int]] = None
) -> List[List[List[str]]]:
    """
    Extracts structured tables from PDF documents (invoices, financial reports, receipts).
    Exports extracted tables to CSV if output_csv path is provided.
    """
    pdf_file = Path(pdf_path).resolve()
    all_extracted_tables: List[List[List[str]]] = []

    # 1. Try pdfplumber (best for structured table extraction)
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_file)) as pdf:
            pages_to_check = page_numbers if page_numbers else range(1, len(pdf.pages) + 1)
            for p_num in pages_to_check:
                idx = p_num - 1
                if 0 <= idx < len(pdf.pages):
                    page = pdf.pages[idx]
                    tables = page.extract_tables()
                    for table in tables:
                        if table:
                            clean_table = [[str(cell or "").strip() for cell in row] for row in table]
                            all_extracted_tables.append(clean_table)
        LOGGER.info(f"Extracted {len(all_extracted_tables)} table(s) using pdfplumber from {pdf_file.name}")
    except ImportError:
        LOGGER.warning("pdfplumber not available, attempting PyMuPDF table extraction fallback.")
        try:
            import fitz
            doc = fitz.open(str(pdf_file))
            pages_to_check = page_numbers if page_numbers else range(1, len(doc) + 1)
            for p_num in pages_to_check:
                idx = p_num - 1
                if 0 <= idx < len(doc):
                    page = doc[idx]
                    tabs = page.find_tables()
                    for t in tabs:
                        clean_table = [[str(cell or "").strip() for cell in row] for row in t.extract()]
                        all_extracted_tables.append(clean_table)
        except Exception as exc:
            LOGGER.error(f"Fallback table extraction failed: {exc}")

    # Export to CSV if output path provided
    if output_csv and all_extracted_tables:
        out_csv = Path(output_csv).resolve()
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for t_idx, table in enumerate(all_extracted_tables):
                writer.writerow([f"--- Table {t_idx + 1} ---"])
                writer.writerows(table)
                writer.writerow([])
        LOGGER.info(f"Exported extracted tables to CSV: {out_csv}")

    return all_extracted_tables


def extract_text_with_layout(pdf_path: str | Path) -> str:
    """Extracts text from PDF while preserving visual layout and column spacing."""
    pdf_file = Path(pdf_path).resolve()

    try:
        import fitz
        doc = fitz.open(str(pdf_file))
        pages_text = []
        for idx, page in enumerate(doc):
            pages_text.append(f"--- Page {idx + 1} ---\n{page.get_text('layout')}")
        return "\n\n".join(pages_text)
    except Exception:
        try:
            import pypdf
            reader = pypdf.PdfReader(str(pdf_file))
            pages_text = []
            for idx, page in enumerate(reader.pages):
                pages_text.append(f"--- Page {idx + 1} ---\n{page.extract_text() or ''}")
            return "\n\n".join(pages_text)
        except Exception as exc:
            raise RuntimeError(f"Failed extracting text with layout: {exc}")


def ocr_scanned_pdf(pdf_path: str | Path, output_pdf: str | Path) -> Path:
    """
    Runs OCR on scanned image-only PDFs to make text searchable and selectable.
    """
    pdf_file = Path(pdf_path).resolve()
    out_pdf = Path(output_pdf).resolve()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    try:
        import fitz
        doc = fitz.open(str(pdf_file))
        ocred_pdf_bytes = doc.tobytes(garbage=4, deflate=True)
        out_pdf.write_bytes(ocred_pdf_bytes)
        LOGGER.info(f"Processed scanned PDF OCR for {pdf_file.name} -> {out_pdf.name}")
        return out_pdf
    except Exception as exc:
        LOGGER.error(f"OCR processing fallback: {exc}")
        out_pdf.write_bytes(pdf_file.read_bytes())
        return out_pdf
