"""Symmetric encryption for OCR-extracted document text.

WHY
---
Uploaded documents (Aadhaar, bank passbook, death certificate) contain PII.
Once server-side OCR has pulled the text off the image we do NOT want the raw
text sitting unencrypted in the SQLite row. This module encrypts the extracted
text at rest with AES-GCM and hands plaintext to the LLM just-in-time.

KEY
---
32-byte key, base64-encoded, in env var OCR_ENCRYPTION_KEY. In dev / demo mode
(no key set) we generate a per-process ephemeral key so the code path still
runs end-to-end — but any restart makes the ciphertext unreadable, which is
the right default: rotate the container, lose the plaintext.
"""

import base64
import os
import secrets

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _CRYPTO_OK = True
except BaseException:  # pragma: no cover
    # BaseException on purpose: pyo3's PanicException (raised when the
    # installed cryptography wheel has a broken native binding) doesn't
    # subclass Exception. Failing closed to plaintext is safer than crashing
    # boot; we log the condition so it's obvious in the health check.
    AESGCM = None  # type: ignore
    _CRYPTO_OK = False


_PREFIX = "enc-gcm:v1:"  # marks stored ciphertext so plaintext can migrate in


def _load_key() -> bytes:
    raw = os.getenv("OCR_ENCRYPTION_KEY", "").strip()
    if raw:
        try:
            key = base64.b64decode(raw)
            if len(key) in (16, 24, 32):
                return key
            print(f"[crypto] OCR_ENCRYPTION_KEY wrong length ({len(key)} bytes) — regenerating")
        except Exception:
            print("[crypto] OCR_ENCRYPTION_KEY not valid base64 — regenerating")
    # Ephemeral key: fine for dev, and safer than "no encryption".
    return secrets.token_bytes(32)


_KEY = _load_key() if _CRYPTO_OK else b""
_HAS_ENV_KEY = bool(os.getenv("OCR_ENCRYPTION_KEY", "").strip()) and _CRYPTO_OK
enabled = _CRYPTO_OK

if not _CRYPTO_OK:
    print("[crypto] cryptography package not available — OCR text stored plaintext")
elif not _HAS_ENV_KEY:
    print("[crypto] using ephemeral AES-GCM key (set OCR_ENCRYPTION_KEY for durable encryption)")
else:
    print("[crypto] AES-GCM enabled with configured OCR_ENCRYPTION_KEY")


def encrypt(plaintext: str) -> str:
    """Return a self-describing string safe to store in a text column."""
    if not _CRYPTO_OK or not plaintext:
        return plaintext
    nonce = secrets.token_bytes(12)
    ct = AESGCM(_KEY).encrypt(nonce, plaintext.encode("utf-8"), None)
    return _PREFIX + base64.b64encode(nonce + ct).decode("ascii")


def decrypt(stored: str) -> str:
    """Decrypt a value produced by encrypt(); pass-through for legacy plaintext."""
    if not stored or not stored.startswith(_PREFIX) or not _CRYPTO_OK:
        return stored
    blob = base64.b64decode(stored[len(_PREFIX):])
    nonce, ct = blob[:12], blob[12:]
    try:
        return AESGCM(_KEY).decrypt(nonce, ct, None).decode("utf-8")
    except Exception as e:
        # An ephemeral key that changed at restart lands here — surface it
        # explicitly instead of returning garbage or crashing the request.
        print(f"[crypto] decrypt failed ({str(e)[:80]}); returning empty")
        return ""


def is_encrypted(stored: str) -> bool:
    return bool(stored) and stored.startswith(_PREFIX)
