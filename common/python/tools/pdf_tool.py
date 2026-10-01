from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from utils.logging import get_logger

from tools.pdf_converter import convert_document
from tools.pdf_manipulator import merge_pdfs, split_pdf, rotate_pdf_pages, reorder_pdf_pages
from tools.pdf_extractor import extract_tables_from_pdf, extract_text_with_layout, ocr_scanned_pdf
from tools.pdf_security import add_watermark_to_pdf, add_page_numbers_to_pdf, redact_sensitive_data_in_pdf

LOGGER = get_logger("blinky.pdf_tool")


def resolve_explorer_pdf_context() -> Dict[str, Any]:
    """
    Queries active Windows File Explorer windows to auto-detect open folder path
    and highlighted/selected PDF, DOCX, TXT, or Image files.
    """
    active_folder = None
    selected_files: List[Path] = []

    try:
        import win32com.client
        shell = win32com.client.Dispatch("Shell.Application")
        for window in shell.Windows():
            try:
                # Filter for Explorer windows
                if "explorer.exe" in str(window.FullName).lower():
                    doc = window.Document
                    active_folder = Path(doc.Folder.Self.Path)
                    selected_items = doc.SelectedItems()
                    for i in range(selected_items.Count):
                        item_path = Path(selected_items.Item(i).Path)
                        if item_path.suffix.lower() in {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}:
                            selected_files.append(item_path)
                    break
            except Exception:
                continue
    except Exception as exc:
        LOGGER.warning(f"Could not query Windows File Explorer COM interface: {exc}")

    # Fallback to current working directory if Explorer query yielded no files
    if not selected_files and active_folder and active_folder.exists():
        for candidate in active_folder.iterdir():
            if candidate.suffix.lower() in {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}:
                selected_files.append(candidate)

    return {
        "active_folder": str(active_folder) if active_folder else str(Path.cwd()),
        "selected_files": [str(f) for f in selected_files],
    }


def handle_pdf_action(action: str, params: dict) -> Dict[str, Any]:
    """
    Unified entry point dispatcher for all PDF and document conversion tools.
    Automatically resolves highlighted File Explorer files if input_file is omitted.
    """
    clean_action = action.lower().strip()

    # Auto-resolve Explorer context if file inputs missing
    explorer_context = resolve_explorer_pdf_context()
    default_files = explorer_context.get("selected_files", [])

    if clean_action in {"convert", "convert_document"}:
        input_file = params.get("input_file") or params.get("file_path") or params.get("input_path") or (default_files[0] if default_files else None)
        if not input_file:
            raise ValueError("No input file provided or highlighted in File Explorer.")
        target_fmt = params.get("target_format") or params.get("to", "pdf")
        output_path = params.get("output_path")
        res = convert_document(input_file, target_fmt, output_path=output_path)
        return res

    elif clean_action in {"merge", "merge_pdfs"}:
        pdf_paths = params.get("pdf_paths") or params.get("files") or default_files
        if not pdf_paths:
            raise ValueError("No PDF files provided or highlighted in File Explorer to merge.")
        output_pdf = params.get("output_pdf") or params.get("output_path") or "merged_output.pdf"
        res_path = merge_pdfs(pdf_paths, output_pdf)
        return {"success": True, "output_path": str(res_path), "action": "merge"}

    elif clean_action in {"split", "split_pdf", "extract_pages"}:
        pdf_path = params.get("pdf_path") or params.get("input_file") or (default_files[0] if default_files else None)
        if not pdf_path:
            raise ValueError("No PDF file provided or highlighted in File Explorer.")
        output_dir = params.get("output_dir") or "split_output"
        page_range = params.get("page_range")
        res_files = split_pdf(pdf_path, output_dir, page_range=page_range)
        return {"success": True, "output_paths": [str(p) for p in res_files], "action": "split"}

    elif clean_action in {"rotate", "rotate_pdf"}:
        pdf_path = params.get("pdf_path") or params.get("input_file") or (default_files[0] if default_files else None)
        if not pdf_path:
            raise ValueError("No PDF file provided or highlighted in File Explorer.")
        output_pdf = params.get("output_pdf") or pdf_path
        degrees = int(params.get("degrees", 90))
        page_numbers = params.get("page_numbers")
        res_path = rotate_pdf_pages(pdf_path, output_pdf, degrees=degrees, page_numbers=page_numbers)
        return {"success": True, "output_path": str(res_path), "action": "rotate"}

    elif clean_action in {"reorder", "reorder_pdf"}:
        pdf_path = params.get("pdf_path") or params.get("input_file") or (default_files[0] if default_files else None)
        if not pdf_path:
            raise ValueError("No PDF file provided or highlighted in File Explorer.")
        output_pdf = params.get("output_pdf") or pdf_path
        order = params.get("order") or []
        res_path = reorder_pdf_pages(pdf_path, output_pdf, order)
        return {"success": True, "output_path": str(res_path), "action": "reorder"}

    elif clean_action in {"extract_tables", "table_to_csv"}:
        pdf_path = params.get("pdf_path") or params.get("input_file") or (default_files[0] if default_files else None)
        if not pdf_path:
            raise ValueError("No PDF file provided or highlighted in File Explorer.")
        output_csv = params.get("output_csv") or "extracted_tables.csv"
        tables = extract_tables_from_pdf(pdf_path, output_csv=output_csv)
        return {"success": True, "output_csv": str(output_csv), "table_count": len(tables)}

    elif clean_action in {"watermark", "add_watermark"}:
        pdf_path = params.get("pdf_path") or params.get("input_file") or (default_files[0] if default_files else None)
        if not pdf_path:
            raise ValueError("No PDF file provided or highlighted in File Explorer.")
        output_pdf = params.get("output_pdf") or pdf_path
        text = params.get("text", "CONFIDENTIAL")
        res_path = add_watermark_to_pdf(pdf_path, output_pdf, watermark_text=text)
        return {"success": True, "output_path": str(res_path), "action": "watermark"}

    elif clean_action in {"page_numbers", "add_page_numbers"}:
        pdf_path = params.get("pdf_path") or params.get("input_file") or (default_files[0] if default_files else None)
        if not pdf_path:
            raise ValueError("No PDF file provided or highlighted in File Explorer.")
        output_pdf = params.get("output_pdf") or pdf_path
        res_path = add_page_numbers_to_pdf(pdf_path, output_pdf)
        return {"success": True, "output_path": str(res_path), "action": "page_numbers"}

    elif clean_action in {"redact", "redact_pdf"}:
        pdf_path = params.get("pdf_path") or params.get("input_file") or (default_files[0] if default_files else None)
        if not pdf_path:
            raise ValueError("No PDF file provided or highlighted in File Explorer.")
        output_pdf = params.get("output_pdf") or pdf_path
        res_path = redact_sensitive_data_in_pdf(pdf_path, output_pdf)
        return {"success": True, "output_path": str(res_path), "action": "redact"}

    elif clean_action in {"ocr", "ocr_pdf"}:
        pdf_path = params.get("pdf_path") or params.get("input_file") or (default_files[0] if default_files else None)
        if not pdf_path:
            raise ValueError("No PDF file provided or highlighted in File Explorer.")
        output_pdf = params.get("output_pdf") or pdf_path
        res_path = ocr_scanned_pdf(pdf_path, output_pdf)
        if params.get("open_in_explorer", True):
            highlight_in_explorer(res_path)
        return {"success": True, "output_path": str(res_path), "action": "ocr"}

    else:
        raise ValueError(f"Unknown PDF tool action: {action}")


def highlight_in_explorer(file_path: str | Path) -> None:
    """Selects and visually highlights the target output file in Windows File Explorer."""
    try:
        import subprocess
        p = Path(file_path).resolve()
        if p.exists() and os.name == "nt":
            subprocess.Popen(["explorer.exe", f"/select,{p}"])
    except Exception as exc:
        LOGGER.warning(f"Could not highlight file in Explorer: {exc}")


def resolve_pdf_request(question: str) -> Optional[Dict[str, Any]]:
    """Deterministic intent matcher for PDF operations."""
    q = question.lower().strip()
    if not any(k in q for k in ["pdf", "docx", "word document", "table to csv", "extract table"]):
        return None

    if any(k in q for k in ["merge", "combine"]) and "pdf" in q:
        return {"pdf_action": "merge"}

    if any(k in q for k in ["split", "extract page", "extract pages"]) and "pdf" in q:
        import re
        m = re.search(r"pages?\s+([\d\s,-]+)", q)
        page_range = m.group(1).strip() if m else None
        return {"pdf_action": "split", "page_range": page_range}

    if "rotate" in q and "pdf" in q:
        deg = 90
        if "180" in q:
            deg = 180
        elif "270" in q:
            deg = 270
        return {"pdf_action": "rotate", "degrees": deg}

    if "watermark" in q or "stamp" in q:
        import re
        m = re.search(r"(?:watermark|stamp)\s+(?:['\"](.*?)['\"]|([A-Za-z0-9_-]+))", question, re.IGNORECASE)
        text = (m.group(1) or m.group(2) or "CONFIDENTIAL") if m else "CONFIDENTIAL"
        return {"pdf_action": "watermark", "text": text}

    if "page number" in q or "page numbers" in q:
        return {"pdf_action": "page_numbers"}

    if any(k in q for k in ["extract table", "extract tables", "table to csv"]):
        return {"pdf_action": "extract_tables"}

    if any(k in q for k in ["redact", "blackout", "black out"]):
        return {"pdf_action": "redact"}

    if any(k in q for k in ["ocr", "make searchable", "searchable pdf"]):
        return {"pdf_action": "ocr"}

    if "convert" in q or "turn" in q or "export" in q:
        target_fmt = "pdf"
        if "to docx" in q or "to word" in q:
            target_fmt = "docx"
        elif "to png" in q or "to image" in q or "to images" in q or "to jpg" in q:
            target_fmt = "png"
        return {"pdf_action": "convert", "target_format": target_fmt}

    return None

