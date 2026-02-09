import easyocr

# Initialize reader once (downloads model on first run)
_reader = None

def get_reader(languages: list[str] = ['en'], gpu: bool = False) -> easyocr.Reader:
    """Get or create EasyOCR reader instance."""
    global _reader
    if _reader is None:
        # verbose=False to disable progress bars that cause encoding issues
        _reader = easyocr.Reader(languages, gpu=gpu, verbose=False)
    return _reader

def extract_text_from_images(images: list[bytes], languages: list[str] = ['en']) -> str:
    """Run OCR on rasterized PDF pages."""
    reader = get_reader(languages)
    full_text = []
    
    for i, img_bytes in enumerate(images):
        print(f"  OCR processing page {i+1}/{len(images)}...")
        # EasyOCR accepts bytes directly
        # detail=0 returns only text, no bounding boxes
        result = reader.readtext(img_bytes, detail=0)
        full_text.extend(result)
    
    return "\n".join(full_text)
