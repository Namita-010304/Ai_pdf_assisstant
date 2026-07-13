import fitz  # PyMuPDF
import os
from PIL import Image
import io

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


def extract_text_from_pdf(file_path: str) -> list[dict]:
    """
    Extract text from a PDF file page by page.
    Falls back to OCR for pages with no extractable text (scanned PDFs).

    Returns a list of dicts: [{"page_number": int, "text": str}]
    """
    pages = []
    doc = fitz.open(file_path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text().strip()

        # If page has no text content, try OCR (gracefully)
        if not text and TESSERACT_AVAILABLE:
            try:
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_bytes))
                text = pytesseract.image_to_string(image, lang="eng+hin").strip()
            except Exception as e:
                print(f"[WARNING] OCR failed for page {page_num + 1}: {e}")
                text = ""

        if text:
            pages.append({
                "page_number": page_num + 1,
                "text": text
            })

    doc.close()
    return pages


def chunk_text(pages: list[dict], doc_id: int, doc_name: str,
               chunk_size: int = 800, overlap: int = 150) -> list[dict]:
    """
    Split page texts into overlapping chunks for better retrieval.

    Returns a list of chunk dicts with doc_id, doc_name, page_number, and text.
    """
    chunks = []
    for page in pages:
        text = page["text"]
        page_number = page["page_number"]
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = text[start:end].strip()
            if len(chunk) > 50:  # skip tiny fragments
                chunks.append({
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "page_number": page_number,
                    "text": chunk
                })
            start += chunk_size - overlap

    return chunks
