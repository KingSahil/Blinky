# Blinky Custom PDF & Format Conversion Engine: Master Implementation Plan

---

## 1. Objective

The objective of the **Blinky Custom PDF Engine** is to provide a local, ultra-fast, privacy-preserving document manipulation and format conversion engine built directly into Blinky's Desktop (Tauri + Python) and Mobile Companion (`Blinky.apk`) ecosystem.

Users can manipulate, convert, extract, watermark, and redact documents using natural language commands without uploading sensitive files to online third-party websites or needing expensive software subscriptions.

---

## 2. User Workflow & Execution Pipeline

```mermaid
graph TD
    subgraph Desktop Workflow (Windows File Explorer)
        A1["User opens folder or selects files in File Explorer"] --> B1["Blinky detects active folder & highlighted files via UIA"]
        B1 --> C1["User speaks/types natural command (e.g. 'Convert to PDF', 'Merge these')"]
        C1 --> D1["Blinky Intent Classifier routes to pdf_tool.py"]
        D1 --> E1["Execution completes in <0.5s & opens output folder in Explorer"]
    end

    subgraph Mobile Companion Workflow
        A2["User picks files in Mobile Companion App"] --> B2["User enters edit prompt e.g. 'Convert DOCX to PDF and watermark'"]
        B2 --> C2["Mobile transfers files over WebSocket Port 9001"]
        C2 --> D1
    end
```

### Detailed Desktop Execution Example:
1. User highlights `report.docx` or opens a folder with 3 PDF files in Windows File Explorer.
2. User triggers Blinky (`Win+Space` or *"Hey Blinky"*) and says:
   * *"Convert this Word document to PDF"*
   * *"Merge all PDFs in this folder and add a CONFIDENTIAL watermark"*
   * *"Extract tables on page 2 to CSV"*
3. Blinky executes the operation locally in sub-second time, opens the target directory, and visually highlights the generated output file.

---

## 3. Complete Feature Matrix

### A. Universal Format Conversion Engine
* **TXT to PDF:** Convert plain text / Markdown files to formatted PDF.
* **DOCX / Word to PDF:** Native conversion of `.docx` files to PDF.
* **PDF to DOCX / Word:** Extract PDF text and layout into editable `.docx`.
* **PDF to Images (PNG/JPG):** Render PDF pages as high-resolution image files.
* **Images to PDF:** Combine multiple PNG/JPG/WEBP images into a single formatted PDF document.

### B. Page Manipulation & Editing
* **Smart Merging:** Combine multiple PDFs in custom sequence.
* **Range Extraction / Splitting:** Extract specific page ranges (e.g., *"Extract pages 1-3 and 8-10"*).
* **Page Rotation & Reordering:** Fix rotated or upside-down pages (*"Rotate page 3 by 90 degrees clockwise"*).

### C. Data Extraction & OCR
* **Structured Table Extraction:** Detect tables in invoices, receipts, or bank statements and export to `.csv` or `.xlsx`.
* **Scanned Image PDF OCR:** Run built-in OCR (Pytesseract / OmniParser) to convert scanned PDF images into searchable, copyable text PDFs.

### D. Watermarking, Security & Redaction
* **Text Watermarking:** Stamp custom text (*"CONFIDENTIAL"*, *"DRAFT"*, *"FOR INTERNAL USE ONLY"*) across all pages.
* **Page Numbering:** Add dynamic *"Page X of Y"* or custom title headers/footers.
* **Sensitive Data Redaction:** Automatically black out sensitive terms (credit cards, passwords, SSNs, phone numbers) before sharing.

### E. OKF Notebook Integration
* **Direct Notebook Ingestion:** Command any PDF in File Explorer to instantly import into the **Blinky OKF Notebook Hub** for grounded Q&A and summary generation.

---

## 4. Multi-Phase Implementation Plan

### Phase 1: Universal Conversion Engine (`common/python/tools/pdf_converter.py`)
* Implement TXT to PDF converter (`reportlab` / `fpdf2`).
* Implement DOCX to PDF and PDF to DOCX converter (`docx2pdf` / `pdf2docx` / `python-docx`).
* Implement PDF to Image (PNG/JPG) converter (`pdf2image` / `pymupdf`).
* Implement Images to PDF converter (`PIL` / `Pillow`).

### Phase 2: Page Manipulation Engine (`common/python/tools/pdf_manipulator.py`)
* Implement PDF merging (`pypdf.PdfMerger`).
* Implement range extraction and page splitting (`pypdf.PdfWriter`).
* Implement page rotation (90°, 180°, 270°) and reordering.

### Phase 3: Data Extraction & Table Parser (`common/python/tools/pdf_extractor.py`)
* Implement structured table extraction to CSV/Excel (`pdfplumber` / `pypdf`).
* Implement OCR scanner for non-searchable image PDFs using Pytesseract / OmniParser.

### Phase 4: Watermarking, Security & Redaction (`common/python/tools/pdf_security.py`)
* Implement text watermark stamping with opacity and angle controls.
* Implement dynamic page numbering (*"Page X of Y"*).
* Implement text redaction (blacking out sensitive regex patterns like SSNs, credit card numbers).

### Phase 5: Agent Tooling & Intent Routing (`common/python/tools/pdf_tool.py` & `main.py`)
* Create unified entry point `pdf_tool.py` routing all PDF operations.
* Add `PDF_ENGINE` intent classification in `main.py` for automatic prompt routing.

### Phase 6: Windows File Explorer Context Integration (`app_context/registry.py`)
* Integrate Windows UIA selected file detector to resolve highlighted PDF/DOCX files directly from File Explorer.
* Add automatic file selection highlighting after generation.

### Phase 7: Mobile Companion File Transfer Integration (`common/mobile/`)
* Extend mobile File Transfer Panel to support instant PDF conversion and editing requests over WebSocket Port 9001.

### Phase 8: Automated Test Suite (`common/python/tests/test_pdf_engine.py`)
* Comprehensive unit test suite testing conversion, merging, splitting, watermarking, and table extraction.
