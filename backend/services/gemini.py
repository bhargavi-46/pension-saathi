"""GeminiService — thin wrapper around Google Gemini.

Model names are configurable via env (GEMINI_MODEL / GEMINI_EMBED_MODEL) so a
model being retired from the free tier is a one-line .env fix, not a code
change. Defaults target the current free-tier models.

If GOOGLE_API_KEY is not set, the service runs in MOCK mode: chat/vision/embed
return deterministic canned output so the whole app can be demoed end-to-end
without a key (and without network access).
"""

import hashlib
import json
import math
import os
import re

from dotenv import load_dotenv

from services.groq_provider import groq_provider

load_dotenv()

EMBED_DIM = 768

DEFAULT_CHAT_MODEL = "gemini-2.5-flash"
DEFAULT_EMBED_MODEL = "gemini-embedding-001"


def is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "quota" in text or "resourceexhausted" in text or "rate limit" in text


# Names that indicate a specialised variant we don't want for chat/vision
_SPECIALISED = ("tts", "image", "live", "audio", "exp", "veo", "imagen", "embedding", "aqa", "gemma")


def _pick_chat_model(genai) -> str:
    """Ask Google which models THIS key can actually use, prefer the rolling
    'latest flash' alias, then the newest general-purpose flash model.
    Avoids hardcoding names that Google keeps retiring for new accounts."""
    try:
        names = [
            m.name.removeprefix("models/")
            for m in genai.list_models()
            if "generateContent" in (getattr(m, "supported_generation_methods", None) or [])
        ]
        for alias in ("gemini-flash-latest", "gemini-flash-lite-latest"):
            if alias in names:
                return alias
        flash = sorted(
            (n for n in names if "flash" in n and not any(s in n for s in _SPECIALISED)),
            reverse=True,  # lexicographic puts higher version numbers first
        )
        if flash:
            return flash[0]
        general = [n for n in names if not any(s in n for s in _SPECIALISED)]
        if general:
            return sorted(general, reverse=True)[0]
    except Exception as e:
        print(f"[gemini] model auto-detect failed ({e}); using default {DEFAULT_CHAT_MODEL}")
    return DEFAULT_CHAT_MODEL


def _pick_embed_model(genai) -> str:
    try:
        names = [
            m.name.removeprefix("models/")
            for m in genai.list_models()
            if "embedContent" in (getattr(m, "supported_generation_methods", None) or [])
        ]
        if DEFAULT_EMBED_MODEL in names:
            return DEFAULT_EMBED_MODEL
        preferred = sorted((n for n in names if "embedding" in n), reverse=True)
        if preferred:
            return preferred[0]
    except Exception:
        pass
    return DEFAULT_EMBED_MODEL


class GeminiService:
    """GOOGLE_API_KEY accepts one key or several comma-separated keys
    (key1,key2). On a free-tier rate limit the service rotates to the next
    key and retries, which roughly multiplies the per-minute budget."""

    def __init__(self) -> None:
        raw = os.getenv("GOOGLE_API_KEY", "")
        self.api_keys = [k.strip() for k in raw.split(",") if k.strip() and k.strip() != "your-key-here"]
        self.has_gemini = bool(self.api_keys)
        self.groq = groq_provider
        # "mock" only when NO real provider is configured at all.
        self.mock = not self.has_gemini and not self.groq.enabled
        # Last-resort deterministic output if every real provider fails.
        self.allow_mock_fallback = os.getenv("ALLOW_MOCK_FALLBACK", "1") != "0"
        self._embed_mock = not self.has_gemini  # Groq has no embeddings
        self._key_index = 0
        self.chat_model_name = os.getenv("GEMINI_MODEL", "").strip()
        self.embed_model_name = os.getenv("GEMINI_EMBED_MODEL", "").strip()
        if self.has_gemini:
            import google.generativeai as genai

            genai.configure(api_key=self.api_keys[0])
            self._genai = genai
            # Env override wins; otherwise auto-detect from the live model list
            if not self.chat_model_name:
                self.chat_model_name = _pick_chat_model(genai)
            if not self.embed_model_name:
                self.embed_model_name = _pick_embed_model(genai)
            self._model = genai.GenerativeModel(self.chat_model_name)
        else:
            self.chat_model_name = self.chat_model_name or DEFAULT_CHAT_MODEL
            self.embed_model_name = self.embed_model_name or DEFAULT_EMBED_MODEL
        print(
            f"[ai] providers — gemini: {len(self.api_keys)} key(s) | "
            f"groq fallback: {'on' if self.groq.enabled else 'off'} | "
            f"mock last-resort: {'on' if self.allow_mock_fallback else 'off'}"
        )

    def _rotate_key(self) -> None:
        self._key_index = (self._key_index + 1) % len(self.api_keys)
        self._genai.configure(api_key=self.api_keys[self._key_index])
        self._model = self._genai.GenerativeModel(self.chat_model_name)
        print(f"[gemini] rate limit — rotated to API key #{self._key_index + 1}")

    def _with_rotation(self, fn):
        """Run fn; on a quota error, rotate through the remaining keys."""
        last_exc: Exception | None = None
        for _ in range(len(self.api_keys)):
            try:
                return fn()
            except Exception as e:
                if not is_quota_error(e) or len(self.api_keys) == 1:
                    raise
                last_exc = e
                self._rotate_key()
        raise last_exc  # every key is rate-limited

    def prepare_embeddings(self) -> None:
        """Decide ONCE, before the search index is built, whether embeddings
        can use the real API. If the quota is already exhausted, use mock
        embeddings for the whole index so real/mock vectors never mix.
        (Groq has no embeddings API, so this is Gemini-or-mock.)"""
        if not self.has_gemini:
            self._embed_mock = True
            return
        try:
            self._with_rotation(lambda: self._embed_once("warmup"))
            self._embed_mock = False
        except Exception as e:
            if self.allow_mock_fallback and is_quota_error(e):
                print("[gemini] embedding quota exhausted — using mock embeddings for search index")
                self._embed_mock = True
            else:
                raise

    @property
    def index_tag(self) -> str:
        """Identifies which embedding space the vector index was built in, so
        switching between mock and real mode (or embed models) never mixes
        incompatible vectors in the same ChromaDB collection."""
        return "mock" if self._embed_mock else self.embed_model_name.replace(".", "-")

    # ------------------------------------------------------------------ chat
    def chat(self, prompt: str, system: str | None = None) -> str:
        # Provider chain: Gemini → Groq → mock (last resort)
        if self.has_gemini:
            def call() -> str:
                model = self._model
                if system:
                    model = self._genai.GenerativeModel(self.chat_model_name, system_instruction=system)
                return model.generate_content(prompt).text
            try:
                return self._with_rotation(call)
            except Exception as e:
                if not is_quota_error(e):
                    raise
                print("[ai] Gemini exhausted for chat — falling back to Groq")
        if self.groq.enabled:
            try:
                return self.groq.chat(prompt, system)
            except Exception as e:
                print(f"[ai] Groq chat failed: {str(e)[:120]}")
        if self.allow_mock_fallback:
            return self._mock_chat(prompt, system)
        raise RuntimeError("All AI providers unavailable (rate-limited)")

    # ---------------------------------------------------------------- vision
    def vision(self, image_bytes: bytes, prompt: str) -> str:
        if self.has_gemini:
            try:
                return self._with_rotation(
                    lambda: self._model.generate_content(
                        [{"mime_type": "image/jpeg", "data": image_bytes}, prompt]
                    ).text
                )
            except Exception as e:
                if not is_quota_error(e):
                    raise
                print("[ai] Gemini exhausted for vision — falling back to Groq")
        if self.groq.enabled:
            try:
                return self.groq.vision(image_bytes, prompt)
            except Exception as e:
                print(f"[ai] Groq vision failed: {str(e)[:120]}")
        if self.allow_mock_fallback:
            return self._mock_vision(prompt)
        raise RuntimeError("All AI providers unavailable (rate-limited)")

    # ----------------------------------------------------------------- embed
    def embed(self, text: str) -> list[float]:
        if self._embed_mock:
            return self._mock_embed(text)
        try:
            return self._with_rotation(lambda: self._embed_once(text))
        except Exception as e:
            if self.allow_mock_fallback and is_quota_error(e):
                return self._mock_embed(text)
            raise

    def _embed_once(self, text: str) -> list[float]:
        result = self._genai.embed_content(
            model=f"models/{self.embed_model_name}",
            content=text,
            output_dimensionality=EMBED_DIM,
        )
        return result["embedding"]

    # ------------------------------------------------------------ mock impls
    def _mock_chat(self, prompt: str, system: str | None) -> str:
        """Deterministic canned replies keyed on what the prompt asks for."""
        lowered = (prompt + " " + (system or "")).lower()
        if "json" in lowered and "eligible" in lowered:
            return json.dumps(
                {
                    "eligible": True,
                    "confidence": 0.85,
                    "reasoning": "Profile matches the scheme's widow, income and state criteria.",
                    "estimated_annual_value": 12000,
                    "missing_documents": [],
                }
            )
        if "hindi" in lowered:
            return "नमस्ते! मैं आपकी मदद के लिए यहाँ हूँ।"
        return "(mock mode — set GOOGLE_API_KEY in backend/.env for real Gemini replies)"

    def _mock_vision(self, prompt: str) -> str:
        if "ration card" in prompt.lower():
            return json.dumps(
                {
                    "card_holder_name": "K. Padma",
                    "card_number": "WAP-XXXX-7788",
                    "card_type": "White (BPL)",
                    "address": "Mangalagiri, Guntur District, Andhra Pradesh",
                    "family_members_count": 3,
                }
            )
        if "aadhaar" in prompt.lower():
            return json.dumps(
                {
                    "name": "Sunita Devi",
                    "dob": "1984-03-15",
                    "gender": "Female",
                    "address": "Village Rampur, District Gaya, Bihar",
                    "aadhaar_number": "XXXX-XXXX-4321",
                }
            )
        return json.dumps(
            {
                "deceased_name": "Ramesh Kumar",
                "date_of_death": "2023-08-14",
                "place_of_death": "Gaya, Bihar",
                "cause_of_death": None,
                "certificate_number": "DC-BR-2023-118842",
                "issuing_authority": "Registrar of Births & Deaths, Gaya Nagar Nigam",
            }
        )

    def _mock_embed(self, text: str) -> list[float]:
        """Cheap deterministic embedding: hashed bag-of-words projected to a
        fixed dim.  Similar texts share tokens, so cosine similarity is still
        meaningful enough for demo-quality retrieval."""
        vec = [0.0] * EMBED_DIM
        for token in re.findall(r"\w+", text.lower()):
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % EMBED_DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


gemini_service = GeminiService()
