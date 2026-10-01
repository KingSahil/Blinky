from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from utils.logging import get_logger

LOGGER = get_logger("blinky.pdf_manipulator")


def merge_pdfs(pdf_paths: List[str | Path], output_pdf: str | Path) -> Path:
    """Combines multiple PDF documents into a single output PDF."""
    try:
        import pypdf
        merger = getattr(pypdf, "PdfMerger", pypdf.PdfWriter)()
    except Exception:
        from PyPDF2 import PdfMerger
        merger = PdfMerger()

    out_file = Path(output_pdf).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    for p in pdf_paths:
        path_obj = Path(p).resolve()
        if not path_obj.exists():
            LOGGER.warning(f"Skipping non-existent PDF for merge: {path_obj}")
            continue
        merger.append(str(path_obj))
        count += 1

    if count == 0:
        raise ValueError("No valid PDF files provided to merge.")

    merger.write(str(out_file))
    merger.close()
    LOGGER.info(f"Successfully merged {count} PDF(s) into {out_file}")
    return out_file


def parse_page_ranges(range_str: str, max_pages: int) -> List[int]:
    """
    Parses page range strings like '1-3, 5, 8-10' into 0-indexed page numbers.
    """
    selected_pages = []
    parts = range_str.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                start_str, end_str = part.split("-", 1)
                start_page = int(start_str.strip())
                end_page = int(end_str.strip())
                for p in range(start_page, end_page + 1):
                    if 1 <= p <= max_pages:
                        selected_pages.append(p - 1)
            except ValueError:
                pass
        else:
            try:
                p = int(part)
                if 1 <= p <= max_pages:
                    selected_pages.append(p - 1)
            except ValueError:
                pass
    return selected_pages


def split_pdf(
    pdf_path: str | Path,
    output_dir: str | Path,
    page_range: Optional[str] = None
) -> List[Path]:
    """
    Splits a PDF by page ranges or extracts each page into a separate PDF file.
    """
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        writer_cls = pypdf.PdfWriter
    except ImportError:
        from PyPDF2 import PdfReader, PdfWriter
        reader = PdfReader(str(pdf_path))
        writer_cls = PdfWriter

    in_file = Path(pdf_path).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    total_pages = len(reader.pages)
    saved_files: List[Path] = []

    if page_range:
        # Extract specific range into one output PDF
        page_indices = parse_page_ranges(page_range, total_pages)
        if not page_indices:
            raise ValueError(f"Invalid page range '{page_range}' for total pages {total_pages}")

        writer = writer_cls()
        for idx in page_indices:
            writer.add_page(reader.pages[idx])

        out_path = out_dir / f"{in_file.stem}_extracted.pdf"
        with open(out_path, "wb") as f:
            writer.write(f)
        saved_files.append(out_path)
        LOGGER.info(f"Extracted page range '{page_range}' from {in_file.name} -> {out_path.name}")
    else:
        # Split into individual single-page PDFs
        for idx in range(total_pages):
            writer = writer_cls()
            writer.add_page(reader.pages[idx])
            out_path = out_dir / f"{in_file.stem}_page_{idx + 1}.pdf"
            with open(out_path, "wb") as f:
                writer.write(f)
            saved_files.append(out_path)
        LOGGER.info(f"Split {in_file.name} into {len(saved_files)} single-page PDFs.")

    return saved_files


def rotate_pdf_pages(
    pdf_path: str | Path,
    output_pdf: str | Path,
    degrees: int = 90,
    page_numbers: Optional[List[int]] = None
) -> Path:
    """
    Rotates specific pages or all pages of a PDF by 90, 180, or 270 degrees clockwise.
    """
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        writer_cls = pypdf.PdfWriter
    except ImportError:
        from PyPDF2 import PdfReader, PdfWriter
        reader = PdfReader(str(pdf_path))
        writer_cls = PdfWriter

    in_file = Path(pdf_path).resolve()
    out_file = Path(output_pdf).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    writer = writer_cls()
    total_pages = len(reader.pages)

    target_indices = set(p - 1 for p in page_numbers if 1 <= p <= total_pages) if page_numbers else set(range(total_pages))

    for idx, page in enumerate(reader.pages):
        if idx in target_indices:
            page.rotate(degrees)
        writer.add_page(page)

    with open(out_file, "wb") as f:
        writer.write(f)

    LOGGER.info(f"Rotated {len(target_indices)} page(s) by {degrees}° in {out_file.name}")
    return out_file


def reorder_pdf_pages(
    pdf_path: str | Path,
    output_pdf: str | Path,
    new_page_order: List[int]
) -> Path:
    """
    Reorders the pages of a PDF based on 1-indexed list of page numbers (e.g. [3, 1, 2]).
    """
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        writer_cls = pypdf.PdfWriter
    except ImportError:
        from PyPDF2 import PdfReader, PdfWriter
        reader = PdfReader(str(pdf_path))
        writer_cls = PdfWriter

    in_file = Path(pdf_path).resolve()
    out_file = Path(output_pdf).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    total_pages = len(reader.pages)
    writer = writer_cls()

    for p in new_page_order:
        idx = p - 1
        if 0 <= idx < total_pages:
            writer.add_page(reader.pages[idx])

    with open(out_file, "wb") as f:
        writer.write(f)

    LOGGER.info(f"Reordered {len(new_page_order)} page(s) in {out_file.name}")
    return out_file
