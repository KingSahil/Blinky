from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Any


def parse_pdf_text(filepath: Path) -> str:
    """Extract text from PDF using PyMuPDF (fitz), pypdf, or legacy PyPDF2.

    Raises RuntimeError when no PDF backend is installed or the file cannot
    be read, so callers surface a real error instead of storing an
    "[PDF ... Error: ...]" string as if it were document content.
    """
    backend_errors: list[str] = []

    try:
        import fitz

        try:
            text_chunks: list[str] = []
            doc = fitz.open(str(filepath))
            try:
                for idx, page in enumerate(doc):
                    page_text = page.get_text() or ""
                    if page_text.strip():
                        text_chunks.append(f"--- Page {idx + 1} ---\n{page_text.strip()}")
            finally:
                doc.close()
            if text_chunks:
                return "\n\n".join(text_chunks)
            return "[Empty PDF file]"
        except Exception as exc:
            backend_errors.append(f"PyMuPDF: {exc}")
    except ImportError:
        backend_errors.append("PyMuPDF is not installed")

    for module_name in ("pypdf", "PyPDF2"):
        try:
            module = __import__(module_name, fromlist=["PdfReader"])
        except ImportError:
            backend_errors.append(f"{module_name} is not installed")
            continue
        try:
            reader = module.PdfReader(str(filepath))
            text_chunks = []
            for idx, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_chunks.append(f"--- Page {idx + 1} ---\n{page_text.strip()}")
            if text_chunks:
                return "\n\n".join(text_chunks)
            return "[Empty PDF file]"
        except Exception as exc:
            backend_errors.append(f"{module_name}: {exc}")

    raise RuntimeError(
        f"Cannot parse this PDF ({Path(filepath).name}). "
        + "; ".join(backend_errors)
        + ". Install a PDF backend with: pip install pypdf PyMuPDF"
    )


def parse_source_to_okf(source_name: str, raw_content: str | bytes, file_type: str = "txt") -> Dict[str, Any]:
    """
    Converts a document (PDF, Markdown, TXT, HTML) into high-density OKF structured format.
    Injects clear source headers and section tags for 100% accurate LLM context prompts.
    """
    import base64
    clean_name = Path(source_name).name
    ext = (file_type or Path(source_name).suffix.lstrip(".")).lower()
    
    extracted_text = ""

    if ext == "pdf":
        pdf_bytes = None
        if isinstance(raw_content, bytes):
            pdf_bytes = raw_content
        elif isinstance(raw_content, str):
            p = Path(raw_content)
            if p.is_file():
                try:
                    pdf_bytes = p.read_bytes()
                except Exception:
                    pdf_bytes = None
            elif "base64," in raw_content:
                try:
                    b64_str = raw_content.split("base64,", 1)[1]
                    pdf_bytes = base64.b64decode(b64_str)
                except Exception:
                    pdf_bytes = None
            else:
                try:
                    pdf_bytes = base64.b64decode(raw_content)
                except Exception:
                    pdf_bytes = None

        if pdf_bytes:
            temp_path = Path("tmp") / "notebooks" / "temp" / clean_name
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_bytes(pdf_bytes)
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
        elif isinstance(raw_content, str):
            p = Path(raw_content)
            if p.is_file():
                try:
                    extracted_text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    extracted_text = raw_content
            else:
                extracted_text = raw_content

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
