"""Minimal DeepSeek/SiliconFlow API client.

The implementation uses the Python standard library so the hackathon MVP keeps
its zero-install startup. DeepSeek handles structured text generation through
Chat Completions; SiliconFlow-hosted BGE-M3 handles semantic embeddings. A pure
OpenAI text or embedding path remains available through configuration.
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


class JourneybackLLMClient:
    """Route structured generation and embeddings to their configured providers."""

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
        if not self.settings.llm_configured:
            key_name = "DEEPSEEK_API_KEY" if self.settings.llm_provider == "deepseek" else "OPENAI_API_KEY"
            raise LLMConfigurationError(
                f"Text generation is not configured. Add {key_name} to the project .env file."
            )
        if self.settings.llm_provider == "deepseek":
            return self._deepseek_structured(
                instructions=instructions,
                input_text=input_text,
                schema_name=schema_name,
                schema=schema,
            )
        return self._openai_structured(
            instructions=instructions,
            input_text=input_text,
            schema_name=schema_name,
            schema=schema,
        )

    def _openai_structured(
        self,
        *,
        instructions: str,
        input_text: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
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
        response = self._post(
            api_base=self.settings.llm_api_base,
            api_key=self.settings.llm_api_key,
            path="/responses",
            payload=payload,
            provider="OpenAI Responses",
        )
        output_text = _extract_output_text(response)
        return _parse_and_validate(output_text, schema)

    def _deepseek_structured(
        self,
        *,
        instructions: str,
        input_text: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        schema_text = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        system_prompt = (
            f"{instructions}\n\n"
            f"Return only valid JSON for `{schema_name}`. The JSON must conform exactly "
            f"to this schema, including required fields and enum values. Do not add aliases, "
            f"explanations or fields that are absent from the schema:\n{schema_text}"
        )
        thinking: dict[str, str]
        # DeepSeek maps a literal "low" effort to its "high" tier. For this
        # latency-sensitive MVP, application-level none/low therefore selects
        # the provider's non-thinking mode instead.
        if self.settings.reasoning_effort in {"none", "low"}:
            thinking = {"type": "disabled"}
        else:
            effort = "max" if self.settings.reasoning_effort in {"xhigh", "max"} else "high"
            thinking = {"type": "enabled", "reasoning_effort": effort}
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_text},
            ],
            "response_format": {"type": "json_object"},
            "thinking": thinking,
            "max_tokens": 4_096,
            "stream": False,
        }
        response = self._post(
            api_base=self.settings.llm_api_base,
            api_key=self.settings.llm_api_key,
            path="/chat/completions",
            payload=payload,
            provider="DeepSeek Chat Completions",
        )
        # DeepSeek's JSON mode guarantees JSON syntax but does not enforce JSON
        # Schema. Ignore provider-added fields that the application never reads,
        # while keeping required fields, known-field types and enums strict.
        return _parse_and_validate(
            _extract_chat_output(response),
            schema,
            discard_unknown_fields=True,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.settings.embedding_configured:
            key_name = (
                "SILICONFLOW_API_KEY"
                if self.settings.embedding_provider == "siliconflow"
                else "OPENAI_API_KEY"
            )
            raise LLMConfigurationError(
                f"Embeddings are not configured. Add {key_name} to the project .env file."
            )
        payload = {
            "model": self.settings.embedding_model,
            "input": texts,
            "encoding_format": "float",
        }
        provider_name = {
            "siliconflow": "SiliconFlow",
            "openai": "OpenAI",
        }.get(self.settings.embedding_provider, self.settings.embedding_provider)
        response = self._post(
            api_base=self.settings.embedding_api_base,
            api_key=self.settings.embedding_api_key,
            path="/embeddings",
            payload=payload,
            provider=f"{provider_name} Embeddings",
        )
        data = response.get("data")
        if not isinstance(data, list):
            raise LLMResponseError("Embedding response is missing data.")
        ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
        embeddings = [item.get("embedding") for item in ordered]
        if len(embeddings) != len(texts) or not all(isinstance(item, list) for item in embeddings):
            raise LLMResponseError("Embedding response does not match the requested inputs.")
        return embeddings

    def _post(
        self,
        *,
        api_base: str,
        api_key: str,
        path: str,
        payload: dict[str, Any],
        provider: str,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{api_base}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = _safe_error_detail(exc)
            raise LLMAPIError(f"{provider} returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise LLMAPIError(f"Could not reach {provider}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMAPIError(f"{provider} request timed out.") from exc
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"{provider} returned a non-JSON response.") from exc
        if not isinstance(parsed, dict):
            raise LLMResponseError(f"{provider} returned an unexpected response shape.")
        return parsed


# Backwards-compatible import name for callers of the original MVP client.
OpenAIResponsesClient = JourneybackLLMClient


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


def _extract_chat_output(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMResponseError("Chat response is missing choices.")
    first = choices[0]
    if not isinstance(first, dict):
        raise LLMResponseError("Chat response contains an invalid choice.")
    if first.get("finish_reason") == "length":
        raise LLMResponseError("Chat response was truncated before the JSON object completed.")
    message = first.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise LLMResponseError("Chat response did not contain JSON output.")
    return content


def _parse_and_validate(
    output_text: str,
    schema: dict[str, Any],
    *,
    discard_unknown_fields: bool = False,
) -> dict[str, Any]:
    try:
        parsed = _decode_json_object(output_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMResponseError("Model returned malformed structured output.") from exc
    if not isinstance(parsed, dict):
        raise LLMResponseError("Model structured output must be a JSON object.")
    if discard_unknown_fields:
        parsed = _discard_unknown_fields(parsed, schema)
    try:
        _validate_schema(parsed, schema)
    except ValueError as exc:
        raise LLMResponseError(f"Model output did not match the requested schema: {exc}") from exc
    return parsed


def _discard_unknown_fields(value: Any, schema: dict[str, Any]) -> Any:
    """Recursively keep only fields declared by a closed JSON schema."""

    expected = schema.get("type")
    if expected == "object" and isinstance(value, dict):
        properties = schema.get("properties", {})
        items = value.items()
        if schema.get("additionalProperties") is False:
            items = ((name, item) for name, item in items if name in properties)
        return {
            name: _discard_unknown_fields(item, properties.get(name, {}))
            for name, item in items
        }
    if expected == "array" and isinstance(value, list):
        item_schema = schema.get("items", {})
        return [_discard_unknown_fields(item, item_schema) for item in value]
    return value


def _decode_json_object(output_text: str) -> Any:
    """Accept provider JSON mode plus the occasional fenced JSON response."""

    candidate = output_text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3 and lines[0].strip().lower() in {"```", "```json"}:
            candidate = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as direct_error:
        start = candidate.find("{")
        if start < 0:
            raise direct_error
        parsed, end = json.JSONDecoder().raw_decode(candidate[start:])
        trailing = candidate[start + end :].strip().strip("`").strip()
        if trailing:
            raise ValueError("Unexpected text followed the JSON object.")
        return parsed


def _validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                raise ValueError(f"{path}.{name} is required")
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                raise ValueError(f"{path} contains unexpected field {sorted(extras)[0]}")
        for name, item in value.items():
            child_schema = properties.get(name)
            if isinstance(child_schema, dict):
                _validate_schema(item, child_schema, f"{path}.{name}")
    elif expected == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path} must be an array")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, f"{path}[{index}]")
    elif expected == "string":
        if not isinstance(value, str):
            raise ValueError(f"{path} must be a string")
    elif expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{path} must be an integer")
    elif expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{path} must be a number")

    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} contains a value outside the allowed enum")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path} is below the minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path} exceeds the maximum")


def _safe_error_detail(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        message = payload.get("error", {}).get("message")
        if isinstance(message, str):
            return message[:300]
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        pass
    return "request failed"
