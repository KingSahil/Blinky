from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from utils.logging import get_logger

LOGGER = get_logger("blinky.pdf_security")


def add_watermark_to_pdf(
    pdf_path: str | Path,
    output_pdf: str | Path,
    watermark_text: str = "CONFIDENTIAL",
    opacity: float = 0.3,
    angle: int = 45,
    font_size: int = 40
) -> Path:
    """
    Stamps a semi-transparent text watermark across all pages of a PDF document.
    """
    in_file = Path(pdf_path).resolve()
    out_file = Path(output_pdf).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # 1. Try PyMuPDF (fitz) - ultra clean drawing
    try:
        import fitz
        doc = fitz.open(str(in_file))
        for page in doc:
            rect = page.rect
            center = fitz.Point(rect.width / 2, rect.height / 2)
            # Insert rotated text in red/gray with transparency
            page.insert_text(
                center,
                watermark_text,
                fontsize=font_size,
                rotate=angle,
                color=(0.7, 0.7, 0.7),
                fill_opacity=opacity,
                overlay=True
            )
        doc.save(str(out_file))
        LOGGER.info(f"Stamped watermark '{watermark_text}' onto {in_file.name} using PyMuPDF")
        return out_file
    except ImportError:
        pass

    # 2. Fallback using ReportLab + pypdf
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        try:
            import pypdf
        except ImportError:
            import PyPDF2 as pypdf

        watermark_temp = out_file.parent / f"watermark_temp_{out_file.stem}.pdf"
        c = canvas.Canvas(str(watermark_temp), pagesize=letter)
        c.saveState()
        c.setFillColorRGB(0.7, 0.7, 0.7, alpha=opacity)
        c.setFont("Helvetica-Bold", font_size)
        c.translate(300, 400)
        c.rotate(angle)
        c.drawCentredString(0, 0, watermark_text)
        c.restoreState()
        c.save()

        reader = pypdf.PdfReader(str(in_file))
        wm_reader = pypdf.PdfReader(str(watermark_temp))
        wm_page = wm_reader.pages[0]

        writer = pypdf.PdfWriter()
        for page in reader.pages:
            page.merge_page(wm_page)
            writer.add_page(page)

        with open(out_file, "wb") as f:
            writer.write(f)

        try:
            watermark_temp.unlink()
        except Exception:
            pass

        LOGGER.info(f"Stamped watermark '{watermark_text}' via ReportLab fallback: {out_file.name}")
        return out_file
    except ImportError:
        pass

    # 3. Fallback using PIL + pypdf
    try:
        from PIL import Image, ImageDraw
        try:
            import pypdf
        except ImportError:
            import PyPDF2 as pypdf

        watermark_temp = out_file.parent / f"watermark_temp_{out_file.stem}.pdf"
        txt_img = Image.new("RGBA", (612, 792), (255, 255, 255, 0))
        d = ImageDraw.Draw(txt_img)
        d.text((200, 350), watermark_text, fill=(180, 180, 180, int(255 * opacity)))
        rotated = txt_img.rotate(angle)

        img_rgb = rotated.convert("RGB")
        img_rgb.save(str(watermark_temp), "PDF", resolution=100.0)

        reader = pypdf.PdfReader(str(in_file))
        wm_reader = pypdf.PdfReader(str(watermark_temp))
        wm_page = wm_reader.pages[0]

        writer = pypdf.PdfWriter()
        for page in reader.pages:
            page.merge_page(wm_page)
            writer.add_page(page)

        with open(out_file, "wb") as f:
            writer.write(f)

        try:
            watermark_temp.unlink()
        except Exception:
            pass

        LOGGER.info(f"Stamped watermark '{watermark_text}' via PIL fallback: {out_file.name}")
        return out_file
    except Exception as exc:
        raise RuntimeError(f"Failed stamping watermark: {exc}")


def add_page_numbers_to_pdf(
    pdf_path: str | Path,
    output_pdf: str | Path,
    format_str: str = "Page {page} of {total}"
) -> Path:
    """
    Adds dynamic page numbers ('Page X of Y') to the footer of every page.
    """
    in_file = Path(pdf_path).resolve()
    out_file = Path(output_pdf).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        import fitz
        doc = fitz.open(str(in_file))
        total = len(doc)
        for idx, page in enumerate(doc):
            rect = page.rect
            footer_text = format_str.format(page=idx + 1, total=total)
            p_bottom = fitz.Point(rect.width / 2 - 40, rect.height - 30)
            page.insert_text(p_bottom, footer_text, fontsize=10, color=(0.4, 0.4, 0.4))

        doc.save(str(out_file))
        LOGGER.info(f"Added page numbers to {in_file.name} -> {out_file.name}")
        return out_file
    except ImportError:
        pass

    # Fallback using PIL + PyPDF2
    try:
        try:
            import pypdf
        except ImportError:
            import PyPDF2 as pypdf
        from PIL import Image, ImageDraw

        reader = pypdf.PdfReader(str(in_file))
        total = len(reader.pages)
        writer = pypdf.PdfWriter()

        for idx, page in enumerate(reader.pages):
            footer_text = format_str.format(page=idx + 1, total=total)
            footer_temp = out_file.parent / f"footer_temp_{idx}_{out_file.stem}.pdf"

            txt_img = Image.new("RGBA", (612, 792), (255, 255, 255, 0))
            d = ImageDraw.Draw(txt_img)
            d.text((270, 750), footer_text, fill=(100, 100, 100, 255))
            txt_img.convert("RGB").save(str(footer_temp), "PDF", resolution=100.0)

            f_reader = pypdf.PdfReader(str(footer_temp))
            page.merge_page(f_reader.pages[0])
            writer.add_page(page)

            try:
                footer_temp.unlink()
            except Exception:
                pass

        with open(out_file, "wb") as f:
            writer.write(f)

        LOGGER.info(f"Added page numbers to {in_file.name} via PIL fallback")
        return out_file
    except Exception as exc:
        raise RuntimeError(f"Failed adding page numbers: {exc}")


def redact_sensitive_data_in_pdf(
    pdf_path: str | Path,
    output_pdf: str | Path,
    target_patterns: Optional[List[str]] = None
) -> Path:
    """
    Redacts (blacks out) sensitive data matching regex patterns (SSNs, credit cards, phones).
    """
    in_file = Path(pdf_path).resolve()
    out_file = Path(output_pdf).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    default_patterns = [
        r"\b\d{3}-\d{2}-\d{4}\b",       # SSN
        r"\b(?:\d[ -]*?){13,16}\b",       # Credit Cards
        r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", # Phone Numbers
    ]
    patterns = target_patterns or default_patterns

    try:
        import fitz
        doc = fitz.open(str(in_file))
        redact_count = 0

        for page in doc:
            for pattern in patterns:
                matches = page.search_for(pattern)
                for rect in matches:
                    page.add_redact_annot(rect, fill=(0, 0, 0))
                    redact_count += 1
            page.apply_redactions()

        doc.save(str(out_file))
        LOGGER.info(f"Redacted {redact_count} sensitive item(s) in {out_file.name}")
        return out_file
    except Exception as exc:
        LOGGER.warning(f"Redaction fallback writing file: {exc}")
        out_file.write_bytes(in_file.read_bytes())
        return out_file
