"""Direct, non-streaming Ollama HTTP chat provider."""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config


class OllamaProviderError(RuntimeError):
    """Raised when the Ollama endpoint cannot return a usable chat response."""


class OllamaProvider:
    """Provider implementation using Ollama's local `/api/chat` endpoint."""

    name = "Ollama"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (base_url or config.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or config.OLLAMA_MODEL
        self.timeout_seconds = (
            config.OLLAMA_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return the model's final message content, excluding thinking data."""
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "options": {"temperature": 0},
        }
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(request_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_bytes = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            if exc.code == 404 and "model" in detail.lower():
                raise OllamaProviderError(
                    f"Ollama model {self.model!r} is unavailable."
                ) from exc
            raise OllamaProviderError(
                f"Ollama returned HTTP {exc.code}."
            ) from exc
        except (TimeoutError, URLError, OSError) as exc:
            if isinstance(exc, URLError):
                reason = exc.reason
                if isinstance(reason, TimeoutError):
                    raise OllamaProviderError("Ollama request timed out.") from exc
            if isinstance(exc, TimeoutError):
                raise OllamaProviderError("Ollama request timed out.") from exc
            raise OllamaProviderError(
                "Could not connect to the local Ollama service."
            ) from exc

        try:
            raw_response = response_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise OllamaProviderError(
                "Ollama returned a response that was not valid UTF-8."
            ) from exc

        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise OllamaProviderError("Ollama returned malformed JSON.") from exc

        message = payload.get("message") if isinstance(payload, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise OllamaProviderError(
                "Ollama response did not contain final message content."
            )

        # Qwen thinking is disabled in the request. Strip any tagged thought
        # blocks defensively; only the final JSON content is passed onward.
        final_content = re.sub(
            r"<think>.*?</think>", "", content, flags=re.IGNORECASE | re.DOTALL
        ).strip()
        if not final_content:
            raise OllamaProviderError("Ollama returned no final response content.")
        return final_content
