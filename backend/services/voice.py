"""Server-side voice — Speech-to-Text and Text-to-Speech for the WhatsApp
channel (where the browser's Web Speech API is not available).

Providers are configurable via env:
  TTS_PROVIDER = elevenlabs | sarvam   (default: elevenlabs)
  STT_PROVIDER = sarvam | elevenlabs   (default: sarvam — best for Indian langs)

Keys:
  ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
  SARVAM_API_KEY

If no key is set the service is disabled (returns None / "") and the WhatsApp
channel simply falls back to text — nothing crashes.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
# A multilingual voice id; override with your chosen ElevenLabs voice.
ELEVEN_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM").strip()
SARVAM_KEY = os.getenv("SARVAM_API_KEY", "").strip()
# Sarvam is the default for BOTH sides of the voice path — its voices are
# tuned for Indian languages and accents, which is what our users speak.
# Override either with TTS_PROVIDER / STT_PROVIDER (e.g. TTS_PROVIDER=elevenlabs).
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "sarvam").strip().lower()
STT_PROVIDER = os.getenv("STT_PROVIDER", "sarvam").strip().lower()

# Map our app language codes -> Sarvam language codes
SARVAM_LANG = {"hi": "hi-IN", "te": "te-IN", "en": "en-IN", "ta": "ta-IN", "bn": "bn-IN"}


class VoiceService:
    def __init__(self) -> None:
        self.tts_enabled = bool(ELEVEN_KEY or SARVAM_KEY)
        self.stt_enabled = bool(SARVAM_KEY or ELEVEN_KEY)
        print(
            f"[voice] TTS: {'on' if self.tts_enabled else 'off'} ({TTS_PROVIDER}) | "
            f"STT: {'on' if self.stt_enabled else 'off'} ({STT_PROVIDER})"
        )

    # ---------------------------------------------------------- Text -> Speech
    def text_to_speech(self, text: str, lang: str = "hi") -> bytes | None:
        """Return spoken audio (mp3/wav bytes) for `text`, or None if disabled."""
        try:
            if TTS_PROVIDER == "sarvam" and SARVAM_KEY:
                return self._sarvam_tts(text, lang)
            if ELEVEN_KEY:
                return self._eleven_tts(text)
            if SARVAM_KEY:
                return self._sarvam_tts(text, lang)
        except requests.HTTPError as e:
            body = e.response.text[:300] if e.response is not None else ""
            print(f"[voice] TTS failed: {str(e)[:120]} | body: {body}")
        except Exception as e:
            print(f"[voice] TTS failed: {str(e)[:120]}")
        return None

    def _eleven_tts(self, text: str) -> bytes:
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}",
            headers={"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.content  # mp3

    def _sarvam_tts(self, text: str, lang: str) -> bytes:
        import base64

        r = requests.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"api-subscription-key": SARVAM_KEY, "Content-Type": "application/json"},
            json={
                "inputs": [text],
                "target_language_code": SARVAM_LANG.get(lang, "hi-IN"),
                "speaker": "anushka",
                "model": "bulbul:v2",
            },
            timeout=60,
        )
        r.raise_for_status()
        return base64.b64decode(r.json()["audios"][0])  # wav

    # ---------------------------------------------------------- Speech -> Text
    def speech_to_text(self, audio_bytes: bytes, lang: str = "hi") -> str:
        """Transcribe a voice note to text, or "" if disabled/failed."""
        try:
            if STT_PROVIDER == "sarvam" and SARVAM_KEY:
                return self._sarvam_stt(audio_bytes, lang)
            if ELEVEN_KEY:
                return self._eleven_stt(audio_bytes)
            if SARVAM_KEY:
                return self._sarvam_stt(audio_bytes, lang)
        except Exception as e:
            print(f"[voice] STT failed: {str(e)[:120]}")
        return ""

    def _sarvam_stt(self, audio_bytes: bytes, lang: str) -> str:
        r = requests.post(
            "https://api.sarvam.ai/speech-to-text",
            headers={"api-subscription-key": SARVAM_KEY},
            files={"file": ("audio.ogg", audio_bytes, "audio/ogg")},
            data={"language_code": SARVAM_LANG.get(lang, "hi-IN"), "model": "saarika:v1"},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("transcript", "")

    def _eleven_stt(self, audio_bytes: bytes) -> str:
        r = requests.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": ELEVEN_KEY},
            files={"file": ("audio.ogg", audio_bytes, "audio/ogg")},
            data={"model_id": "scribe_v1"},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("text", "")


voice_service = VoiceService()
