from __future__ import annotations

import re

from google import genai
from google.genai import types

from config.settings import get_settings

_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


class GeminiClient:
    """Thin wrapper around the google-genai SDK. Isolating the SDK calls here
    means swapping LLM backends later touches only this file."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model_name = settings.model_name

    def generate(self, messages: list[dict]) -> str:
        """messages: ordered list of {"role": "user"|"model", "content": str}.

        Returns the Python code extracted from the model's response (stripped
        of the surrounding markdown fence).
        """
        contents = [
            types.Content(role=m["role"], parts=[types.Part.from_text(text=m["content"])])
            for m in messages
        ]
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
        )
        return extract_code(response.text or "")


def extract_code(text: str) -> str:
    match = _CODE_BLOCK_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()
