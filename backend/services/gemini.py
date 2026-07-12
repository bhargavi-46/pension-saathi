"""GeminiService — thin wrapper around Google Gemini 2.0 Flash.

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

load_dotenv()

EMBED_DIM = 768


class GeminiService:
    def __init__(self) -> None:
        self.api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        self.mock = self.api_key in ("", "your-key-here")
        if not self.mock:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self._genai = genai
            self._model = genai.GenerativeModel("gemini-2.0-flash")

    # ------------------------------------------------------------------ chat
    def chat(self, prompt: str, system: str | None = None) -> str:
        if self.mock:
            return self._mock_chat(prompt, system)
        model = self._model
        if system:
            import google.generativeai as genai

            model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=system)
        return model.generate_content(prompt).text

    # ---------------------------------------------------------------- vision
    def vision(self, image_bytes: bytes, prompt: str) -> str:
        if self.mock:
            return self._mock_vision(prompt)
        response = self._model.generate_content(
            [{"mime_type": "image/jpeg", "data": image_bytes}, prompt]
        )
        return response.text

    # ----------------------------------------------------------------- embed
    def embed(self, text: str) -> list[float]:
        if self.mock:
            return self._mock_embed(text)
        result = self._genai.embed_content(model="models/text-embedding-004", content=text)
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
