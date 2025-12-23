import json
import os
from typing import Dict, Optional

import requests


class AIExtractor:
    """Gemini-based extractor that returns JSON dicts from email body text."""

    def __init__(
        self,
        api_key_env: str = "GEMINI_API_KEY",
        model: str = "gemini-1.5-flash",
        timeout: int = 30,
        endpoint_base: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        self.api_key = os.getenv(api_key_env, "")
        self.model = model
        self.timeout = timeout
        self.endpoint_base = endpoint_base.rstrip("/")

    def _build_prompt(self, body_text: str, schema: Dict[str, str]) -> str:
        schema_lines = "\n".join(f"- {k}: {v}" for k, v in schema.items())
        return (
            "You are an extraction engine. Return ONLY valid JSON.\n"
            "Do not use markdown, code fences, or extra commentary.\n"
            "Use exactly the keys in the schema; no extra keys.\n"
            "If a field is missing, return an empty string for that key.\n"
            "All values must be strings.\n"
            "Keep summaries concise and fact-based.\n"
            "Ignore greetings, auto-send notices, signatures, and legal disclaimers.\n"
            "Ignore boilerplate such as: \"各位\", \"自動送信\", \"送信専用\".\n"
            "Schema:\n"
            f"{schema_lines}\n"
            "Email body (between the markers):\n"
            "-----BEGIN EMAIL-----\n"
            f"{body_text}\n"
            "-----END EMAIL-----"
        )

    def extract_json(
        self,
        body_text: str,
        schema: Dict[str, str],
        system_prompt: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        if not self.api_key:
            return None

        prompt = self._build_prompt(body_text, schema)
        if system_prompt:
            prompt = f"{system_prompt}\n\n{prompt}"

        url = f"{self.endpoint_base}/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]},
            ]
        }

        try:
            resp = requests.post(url, params=params, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except Exception:
            return None
