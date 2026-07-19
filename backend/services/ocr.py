"""Server-side OCR for uploaded documents.

WHY
---
We used to ship the raw image bytes to Google's Vision endpoint. That means
Aadhaar / bank / death-certificate pixels leave our server. This module runs
OCR *locally* with Tesseract (via pytesseract), so only the extracted text —
which we then encrypt at rest — ever goes over the wire to the LLM.

If pytesseract / the tesseract binary isn't installed, the service is
disabled and callers can fall back to their previous path. That keeps the
demo bootable in constrained environments (Render free tier without the
tesseract apt package, e.g.) while making local OCR the default when it is
available.

Language packs
--------------
Indian documents are bilingual (script + English). We ask tesseract to try
Hindi + English by default; override with OCR_LANGS (e.g. "tel+eng"). The
underlying trained data (`tesseract-ocr-hin`, `tesseract-ocr-tel`, …) must be
installed at the OS level for non-English scripts.
"""

import io
import os


def _lazy_imports():
    """Import heavy deps only when OCR is actually invoked."""
    from PIL import Image  # noqa: WPS433 — deliberate late import
    import pytesseract  # noqa: WPS433

    # Windows quirk: even after installing Tesseract, the .exe often isn't on
    # PATH inside the venv / uvicorn subprocess. TESSERACT_CMD lets the
    # operator point us straight at the binary, bypassing PATH entirely.
    cmd = os.getenv("TESSERACT_CMD", "").strip()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    return Image, pytesseract


class OCRService:
    def __init__(self) -> None:
        self.langs = os.getenv("OCR_LANGS", "hin+eng").strip() or "hin+eng"
        self.enabled = self._probe()
        print(
            f"[ocr] server-side OCR — {'on' if self.enabled else 'off'} "
            f"(langs: {self.langs})"
        )

    def _probe(self) -> bool:
        try:
            _, pytesseract = _lazy_imports()
            pytesseract.get_tesseract_version()
            return True
        except Exception as e:  # pytesseract missing OR tesseract binary missing
            print(f"[ocr] disabled: {str(e)[:120]}")
            return False

    def extract(self, image_bytes: bytes, lang: str | None = None) -> str:
        """Return OCR text. Empty string on failure — caller decides fallback."""
        if not self.enabled:
            return ""
        try:
            Image, pytesseract = _lazy_imports()
            img = Image.open(io.BytesIO(image_bytes))
            # OCR quality on phone photos improves noticeably in grayscale
            if img.mode not in ("L", "RGB"):
                img = img.convert("RGB")
            return pytesseract.image_to_string(img, lang=lang or self.langs).strip()
        except Exception as e:
            print(f"[ocr] extraction failed: {str(e)[:120]}")
            return ""


ocr_service = OCRService()
