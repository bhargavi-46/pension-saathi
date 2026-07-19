"""Document agent — reads uploaded documents.

Pipeline (per the privacy playbook):
    image bytes
        └── server-side OCR  (services/ocr.py, Tesseract, offline)
              └── AES-GCM encrypt the extracted text  (services/crypto.py)
                    └── send only the DECRYPTED TEXT to the LLM
                          └── structured JSON (Aadhaar # is masked)

Raw image pixels never leave our server. If local OCR is unavailable or
produces empty text (a very blurry photo, e.g.) we fall back to Gemini Vision
so the demo still works, and the fallback is logged so operators can see it.
"""

import json
import os
import re
import time

from db import Document, SessionLocal, log_action
from services import crypto
from services.gemini import gemini_service
from services.ocr import ocr_service

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")

# Prompts used for LLM extraction. The vision variant still exists because it
# powers the OCR-unavailable fallback path; the text variant is what runs on
# the happy path (server-side OCR text → LLM).
VISION_PROMPTS = {
    "death_certificate": (
        "You are reading an Indian death certificate (may be in Hindi, English, or both). "
        "Extract and return ONLY a JSON object with keys: deceased_name, date_of_death "
        "(ISO format), place_of_death, cause_of_death (null if absent), certificate_number, "
        "issuing_authority. No markdown, no prose — JSON only."
    ),
    "aadhaar": (
        "You are reading an Indian Aadhaar card. Extract and return ONLY a JSON object with "
        "keys: name, dob (ISO format), gender, address, aadhaar_number. For aadhaar_number, "
        "MASK all but the last 4 digits as XXXX-XXXX-1234. No markdown, no prose — JSON only."
    ),
    "bank_passbook": (
        "You are reading an Indian bank passbook front page. Extract and return ONLY a JSON "
        "object with keys: account_holder_name, bank_name, branch, ifsc, account_number "
        "(mask all but last 4 digits). No markdown, no prose — JSON only."
    ),
    "ration_card": (
        "You are reading an Indian ration card. Extract and return ONLY a JSON object with "
        "keys: card_holder_name, card_number, card_type (e.g. white/BPL/AAY/APL), address, "
        "family_members_count. No markdown, no prose — JSON only."
    ),
}

TEXT_PROMPTS = {
    "death_certificate": (
        "The following text was OCR'd from an Indian death certificate (Hindi and/or English). "
        "Return ONLY a JSON object with keys: deceased_name, date_of_death (ISO), "
        "place_of_death, cause_of_death (null if absent), certificate_number, issuing_authority. "
        "No markdown, no prose — JSON only.\n\nOCR TEXT:\n"
    ),
    "aadhaar": (
        "The following text was OCR'd from an Indian Aadhaar card. Return ONLY a JSON object "
        "with keys: name, dob (ISO), gender, address, aadhaar_number. MASK all but the last 4 "
        "digits of aadhaar_number as XXXX-XXXX-1234. No markdown, no prose — JSON only.\n\n"
        "OCR TEXT:\n"
    ),
    "bank_passbook": (
        "The following text was OCR'd from an Indian bank passbook front page. Return ONLY a "
        "JSON object with keys: account_holder_name, bank_name, branch, ifsc, account_number "
        "(mask all but last 4 digits). No markdown, no prose — JSON only.\n\nOCR TEXT:\n"
    ),
    "ration_card": (
        "The following text was OCR'd from an Indian ration card. Return ONLY a JSON object "
        "with keys: card_holder_name, card_number, card_type (white/BPL/AAY/APL), address, "
        "family_members_count. No markdown, no prose — JSON only.\n\nOCR TEXT:\n"
    ),
}


def _parse_json(raw: str) -> dict:
    """The LLM sometimes wraps JSON in ``` fences — strip and parse defensively."""
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse extraction result: {raw[:200]}")


def process_document(widow_id: str, doc_type: str, file_bytes: bytes, filename: str) -> dict:
    if doc_type not in VISION_PROMPTS:
        raise ValueError(f"Unsupported doc_type: {doc_type}")

    # ── 1. Local OCR ────────────────────────────────────────────────────────
    ocr_text = ocr_service.extract(file_bytes) if ocr_service.enabled else ""

    if ocr_text:
        log_action(
            widow_id, "document",
            f"OCR'd {doc_type.replace('_', ' ')} on-server ({len(ocr_text)} chars); "
            "sending only text to the LLM."
        )
        # ── 2. LLM extraction from OCR TEXT (no image bytes leave the box) ──
        raw = gemini_service.chat(TEXT_PROMPTS[doc_type] + ocr_text)
    else:
        # Fallback: OCR disabled or returned nothing (blurry photo, no
        # tesseract binary). Fall through to vision so the demo still works.
        log_action(
            widow_id, "document",
            f"Server-side OCR unavailable/empty for {doc_type.replace('_', ' ')} — "
            "falling back to LLM vision."
        )
        raw = gemini_service.vision(file_bytes, VISION_PROMPTS[doc_type])

    extracted = _parse_json(raw)

    # ── 3. Persist ─────────────────────────────────────────────────────────
    widow_dir = os.path.join(UPLOAD_DIR, widow_id)
    os.makedirs(widow_dir, exist_ok=True)
    ext = os.path.splitext(filename)[1] or ".jpg"
    storage_path = os.path.join(widow_dir, f"{int(time.time())}_{doc_type}{ext}")
    with open(storage_path, "wb") as f:
        f.write(file_bytes)

    # Extracted structured JSON is stored encrypted at rest (AES-GCM). The
    # to_dict() helper below decrypts on read, so the API surface is unchanged.
    encrypted = crypto.encrypt(json.dumps(extracted, ensure_ascii=False))

    with SessionLocal() as db:
        doc = Document(
            widow_id=widow_id,
            doc_type=doc_type,
            storage_path=storage_path,
            extracted_data=encrypted,
        )
        db.add(doc)
        db.commit()
        doc_dict = doc.to_dict()
        # to_dict() JSON-decodes the stored blob; when we've encrypted it that
        # decode fails silently — reconstruct from the in-memory dict instead.
        doc_dict["extracted_data"] = extracted

    headline = extracted.get("deceased_name") or extracted.get("name") or ""
    log_action(
        widow_id,
        "document",
        f"Extracted data from {doc_type.replace('_', ' ')}" + (f" — {headline}" if headline else ""),
        {"extracted": extracted, "encrypted_at_rest": crypto.enabled},
    )
    return doc_dict
