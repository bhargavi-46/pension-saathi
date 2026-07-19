"""Groq fallback provider — real AI (Llama models) used when Gemini is
rate-limited/unavailable. OpenAI-compatible REST API, called with `requests`
so no extra SDK is required.

Get a free key at https://console.groq.com → set GROQ_API_KEY in .env.
Groq has no embeddings endpoint, so embeddings stay on Gemini-or-mock.
"""

import base64
import os

import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Defaults are current Groq production models; override via env if Groq
# retires one (GROQ_MODEL / GROQ_VISION_MODEL).
DEFAULT_TEXT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


class GroqProvider:
    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.enabled = bool(self.api_key)
        self.text_model = os.getenv("GROQ_MODEL", DEFAULT_TEXT_MODEL)
        self.vision_model = os.getenv("GROQ_VISION_MODEL", DEFAULT_VISION_MODEL)

    def _post(self, payload: dict) -> str:
        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def chat(self, prompt: str, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._post({"model": self.text_model, "messages": messages, "temperature": 0.3})

    def vision(self, image_bytes: bytes, prompt: str) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        return self._post(
            {
                "model": self.vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                        ],
                    }
                ],
                "temperature": 0.2,
            }
        )


groq_provider = GroqProvider()
