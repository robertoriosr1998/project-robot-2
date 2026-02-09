import fitz  # PyMuPDF
from pathlib import Path

def load_passwords(passwords_file: str) -> list[str]:
    """Load passwords from file, one per line."""
    path = Path(passwords_file)
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]

def try_open_pdf(pdf_path: str, passwords_list: list[str]) -> fitz.Document | None:
    """Attempt to open PDF, trying passwords if encrypted."""
    doc = fitz.open(pdf_path)
    if doc.is_encrypted:
        # Try empty password first
        if doc.authenticate(""):
            return doc
        for pwd in passwords_list:
            if doc.authenticate(pwd):
                return doc
        return None  # Failed to decrypt
    return doc

def rasterize_pages(doc: fitz.Document, dpi: int = 300) -> list[bytes]:
    """Convert PDF pages to PNG images for OCR."""
    images = []
    for page in doc:
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        images.append(pix.tobytes("png"))
    return images
