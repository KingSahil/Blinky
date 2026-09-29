from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Any


def parse_pdf_text(filepath: Path) -> str:
    """Extract text from PDF using pypdf/PyPDF2 or fallback text extraction."""
    text_chunks = []
    try:
        import pypdf
        reader = pypdf.PdfReader(str(filepath))
        for idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_chunks.append(f"--- Page {idx + 1} ---\n{page_text.strip()}")
    except ImportError:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(filepath))
            for idx, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_chunks.append(f"--- Page {idx + 1} ---\n{page_text.strip()}")
        except Exception as e:
            text_chunks.append(f"[PDF Parsing Error: {e}]")
    except Exception as exc:
        text_chunks.append(f"[PDF Error: {exc}]")

    return "\n\n".join(text_chunks) if text_chunks else "[Empty PDF file]"


def parse_source_to_okf(source_name: str, raw_content: str | bytes, file_type: str = "txt") -> Dict[str, Any]:
    """
    Converts a document (PDF, Markdown, TXT, HTML) into high-density OKF structured format.
    Injects clear source headers and section tags for 100% accurate LLM context prompts.
    """
    clean_name = Path(source_name).name
    ext = (file_type or Path(source_name).suffix.lstrip(".")).lower()
    
    extracted_text = ""

    if ext == "pdf":
        if isinstance(raw_content, bytes):
            temp_path = Path("tmp") / "notebooks" / "temp" / clean_name
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_bytes(raw_content)
            extracted_text = parse_pdf_text(temp_path)
            try:
                temp_path.unlink()
            except Exception:
                pass
        else:
            extracted_text = str(raw_content)
    else:
        if isinstance(raw_content, bytes):
            try:
                extracted_text = raw_content.decode("utf-8")
            except UnicodeDecodeError:
                extracted_text = raw_content.decode("latin-1", errors="ignore")
        else:
            extracted_text = str(raw_content)

    # Clean whitespace while preserving headings and markdown formatting
    lines = [line.rstrip() for line in extracted_text.splitlines()]
    compact_text = "\n".join(lines).strip()

    # Form OKF Structured Block
    okf_block = f"### SOURCE: {clean_name}\nType: {ext.upper()}\n\n{compact_text}\n"

    # Compute word and char counts
    word_count = len(re.findall(r"\w+", compact_text))
    char_count = len(compact_text)

    return {
        "source_name": clean_name,
        "file_type": ext,
        "word_count": word_count,
        "char_count": char_count,
        "okf_content": okf_block,
        "raw_text": compact_text,
    }
