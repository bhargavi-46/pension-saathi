"""WhatsApp Cloud API client — send text/audio, download incoming media.

Configure via env (from Meta's WhatsApp Business Platform):
  WHATSAPP_TOKEN            — permanent access token
  WHATSAPP_PHONE_NUMBER_ID  — the sending phone number's id
  WHATSAPP_VERIFY_TOKEN     — any string you choose (used for webhook setup)

If WHATSAPP_TOKEN is not set the client is disabled: calls are logged and
skipped so the server still runs (useful for local testing of the handler).
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("WHATSAPP_TOKEN", "").strip()
PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "pension-saathi-verify").strip()
GRAPH = "https://graph.facebook.com/v20.0"

enabled = bool(TOKEN and PHONE_ID)


def _headers() -> dict:
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def send_text(to: str, text: str) -> None:
    if not enabled:
        print(f"[whatsapp] (disabled) would send to {to}: {text[:80]}")
        return
    try:
        r = requests.post(
            f"{GRAPH}/{PHONE_ID}/messages",
            headers=_headers(),
            json={"messaging_product": "whatsapp", "to": to, "type": "text",
                  "text": {"body": text}},
            timeout=30,
        )
        if r.status_code >= 400:
            print(f"[whatsapp] send_text HTTP {r.status_code}: {r.text[:300]}")
        else:
            print(f"[whatsapp] send_text OK -> {to}")
    except Exception as e:
        print(f"[whatsapp] send_text failed: {str(e)[:120]}")


def _sniff_audio(audio_bytes: bytes) -> tuple[str, str] | None:
    """Detect the real audio format. Returns (mime, filename) or None if the
    format is not accepted by the WhatsApp Cloud API (e.g. WAV)."""
    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg", "reply.mp3"
    if audio_bytes[:4] == b"OggS":
        return "audio/ogg", "reply.ogg"
    if audio_bytes[4:8] == b"ftyp":
        return "audio/mp4", "reply.m4a"
    if audio_bytes[:4] == b"RIFF":
        return None  # WAV — not supported by WhatsApp
    return None


def send_audio(to: str, audio_bytes: bytes, mime: str = "audio/mpeg") -> None:
    """Upload the audio as media, then send it as a voice message."""
    if not enabled:
        print(f"[whatsapp] (disabled) would send voice note to {to} ({len(audio_bytes)} bytes)")
        return
    sniffed = _sniff_audio(audio_bytes)
    if sniffed is None:
        print(f"[whatsapp] skipping voice note: audio format not supported by WhatsApp "
              f"(first bytes: {audio_bytes[:8]!r})")
        return
    mime, filename = sniffed
    try:
        up = requests.post(
            f"{GRAPH}/{PHONE_ID}/media",
            headers={"Authorization": f"Bearer {TOKEN}"},
            files={"file": (filename, audio_bytes, mime)},
            data={"messaging_product": "whatsapp", "type": mime},
            timeout=60,
        )
        up.raise_for_status()
        media_id = up.json()["id"]
        requests.post(
            f"{GRAPH}/{PHONE_ID}/messages",
            headers=_headers(),
            json={"messaging_product": "whatsapp", "to": to, "type": "audio",
                  "audio": {"id": media_id}},
            timeout=30,
        )
    except Exception as e:
        print(f"[whatsapp] send_audio failed: {str(e)[:120]}")


def download_media(media_id: str) -> bytes | None:
    """Fetch the bytes of an incoming image / voice note by its media id."""
    if not enabled:
        print(f"[whatsapp] (disabled) would download media {media_id}")
        return None
    try:
        meta = requests.get(
            f"{GRAPH}/{media_id}",
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=30,
        )
        meta.raise_for_status()
        url = meta.json()["url"]
        data = requests.get(url, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60)
        data.raise_for_status()
        return data.content
    except Exception as e:
        print(f"[whatsapp] download_media failed: {str(e)[:120]}")
        return None
