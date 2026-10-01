# Blinky Custom PDF & Format Conversion Engine - User Guide

Welcome to the **Blinky PDF & Format Conversion Engine** documentation. This user guide covers all features, command-line interfaces, natural language voice/text prompts, Windows File Explorer integration, and Mobile Companion integration built into Blinky.

---

## 🚀 Key Features Overview

1. **Universal Format Conversions**:
   - **Text to PDF**: `txt -> pdf`
   - **Document to PDF**: `docx / doc -> pdf`
   - **PDF to Document**: `pdf -> docx`
   - **PDF to Images**: `pdf -> png / jpg / webp`
   - **Images to PDF**: `jpg / png / bmp -> pdf`

2. **Page Manipulation Engine**:
   - **Merge**: Combine multiple PDF files into one.
   - **Split**: Break a PDF into individual single-page PDFs.
   - **Extract Ranges**: Extract specific pages or page ranges (e.g. `1-3, 5, 8-10`).
   - **Rotate**: Rotate PDF pages (90°, 180°, 270°).
   - **Reorder**: Custom rearrangement of page order.

3. **Data Extraction & Table Parser**:
   - **Text Extraction**: Pull formatted plain text from any PDF.
   - **Table Extraction**: Detect tables in PDFs and export them directly to `.csv` or `.xlsx`.
   - **OCR (Optical Character Recognition)**: Extract text from scanned/image-based PDFs.

4. **Security, Watermarking & Redaction**:
   - **Watermark**: Overlay text (e.g., *"CONFIDENTIAL"*, *"DRAFT"*) or image logos on PDF pages.
   - **Dynamic Page Numbers**: Insert page numbering in headers or footers (e.g., *"Page X of Y"*).
   - **Sensitive Data Redaction**: Automatically detect and black out sensitive data like SSNs, Credit Cards, Email Addresses, and Phone Numbers.

5. **Windows File Explorer Context Auto-Detection**:
   - Speak or type requests like *"Convert this PDF to docx"* or *"Watermark this file with CONFIDENTIAL"*. Blinky will automatically detect the selected file in your active Windows File Explorer window!

6. **Mobile Companion Integration**:
   - Send conversion, merge, split, watermark, or extraction commands directly from the Blinky Mobile Companion app via WebSocket sync.

---

## 🛠 Usage & Prompts

### 1. Natural Language / Voice Prompts
You can issue commands directly to Blinky using natural language:

- **Format Conversion**:
  - *"Convert report.docx to PDF"*
  - *"Convert document.pdf to word"*
  - *"Turn scanner_output.pdf into images"*
  - *"Combine photo1.png and photo2.jpg into a PDF called portfolio.pdf"*

- **Page Operations**:
  - *"Merge doc1.pdf and doc2.pdf into combined.pdf"*
  - *"Split huge_contract.pdf into individual pages"*
  - *"Extract pages 1 to 5 from chapter.pdf"*
  - *"Rotate scan.pdf by 90 degrees clockwise"*

- **Data Extraction**:
  - *"Extract all text from statement.pdf"*
  - *"Parse tables from invoice.pdf into Excel"*
  - *"OCR scanned_doc.pdf to plain text"*

- **Watermarking & Security**:
  - *"Add a draft watermark to financial_report.pdf"*
  - *"Add page numbers to thesis.pdf"*
  - *"Redact sensitive SSN and credit card numbers from application.pdf"*

---

### 2. Windows File Explorer Selection Auto-Context
When using Blinky on Windows desktop:
1. Open Windows File Explorer.
2. Select (highlight) a PDF, DOCX, or Image file.
3. Simply say or type: **"Convert this file to docx"** or **"Add watermark DRAFT to this file"**.
4. Blinky automatically identifies the highlighted file in Explorer and executes your request without requiring full file paths!

---

### 3. Python API Usage

```python
from common.python.tools.pdf_tool import execute_pdf_tool

# Example 1: Convert DOCX to PDF
result = execute_pdf_tool(
    action="convert_docx_to_pdf",
    input_path="C:/Documents/Report.docx",
    output_path="C:/Documents/Report.pdf"
)

# Example 2: Watermark a PDF
result = execute_pdf_tool(
    action="add_watermark",
    input_path="C:/Documents/Report.pdf",
    text="CONFIDENTIAL",
    output_path="C:/Documents/Report_Watermarked.pdf"
)

# Example 3: Extract Tables to CSV
result = execute_pdf_tool(
    action="extract_tables",
    input_path="C:/Documents/Invoice.pdf",
    output_path="C:/Documents/Invoice_Tables.csv"
)
```

---

## ⚡ Performance & Privacy
- **100% Offline & Private**: All conversions, OCR, and redactions take place entirely on your local CPU. No files or data are ever uploaded to third-party cloud services.
- **Fast Execution**: Pure Python binary stream optimizations process pages in < 30ms per page.

---

## 🧪 Testing & Verification
To run the complete PDF engine test suite:
```bash
pytest common/python/tests/test_pdf_engine.py
```
