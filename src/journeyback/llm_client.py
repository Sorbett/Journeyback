"""Minimal OpenAI Responses and Embeddings API client.

The implementation uses the Python standard library so the hackathon MVP keeps
its zero-install startup. It deliberately exposes a tiny interface that can be
replaced with a test double or another OpenAI-compatible provider.
"""

from __future__ import annotations

import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import LLMSettings


class LLMError(RuntimeError):
    """Base error raised by the model layer."""


class LLMConfigurationError(LLMError):
    """Raised when a live model call is attempted without credentials."""


class LLMAPIError(LLMError):
    """Raised when the provider rejects or cannot complete a request."""


class LLMResponseError(LLMError):
    """Raised when the provider response does not contain the expected output."""


class LLMClient(Protocol):
    """Interface used by the engine and semantic retriever."""

    def structured(
        self,
        *,
        instructions: str,
        input_text: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIResponsesClient:
    """Call Structured Outputs and Embeddings through OpenAI's REST API."""

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings

    def structured(
        self,
        *,
        instructions: str,
        input_text: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "model": self.settings.model,
            "store": False,
            "input": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        if self.settings.reasoning_effort != "none":
            payload["reasoning"] = {"effort": self.settings.reasoning_effort}
        response = self._post("/responses", payload)
        output_text = _extract_output_text(response)
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise LLMResponseError("Model returned malformed structured output.") from exc
        if not isinstance(parsed, dict):
            raise LLMResponseError("Model structured output must be a JSON object.")
        return parsed

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {
            "model": self.settings.embedding_model,
            "input": texts,
            "encoding_format": "float",
        }
        response = self._post("/embeddings", payload)
        data = response.get("data")
        if not isinstance(data, list):
            raise LLMResponseError("Embedding response is missing data.")
        ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
        embeddings = [item.get("embedding") for item in ordered]
        if len(embeddings) != len(texts) or not all(isinstance(item, list) for item in embeddings):
            raise LLMResponseError("Embedding response does not match the requested inputs.")
        return embeddings

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.configured:
            raise LLMConfigurationError(
                "LLM is not configured. Add OPENAI_API_KEY to the project .env file."
            )
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.settings.api_base}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = _safe_error_detail(exc)
            raise LLMAPIError(f"Model API returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise LLMAPIError(f"Could not reach the model API: {exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMAPIError("The model API request timed out.") from exc
        except json.JSONDecodeError as exc:
            raise LLMResponseError("Model API returned a non-JSON response.") from exc
        if not isinstance(parsed, dict):
            raise LLMResponseError("Model API returned an unexpected response shape.")
        return parsed


def _extract_output_text(response: dict[str, Any]) -> str:
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "refusal":
                raise LLMResponseError("The model declined to process this incident.")
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise LLMResponseError("Model response did not contain structured output text.")


def _safe_error_detail(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        message = payload.get("error", {}).get("message")
        if isinstance(message, str):
            return message[:300]
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        pass
    return "request failed"
