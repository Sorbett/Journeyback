from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.config import LLMSettings  # noqa: E402
from journeyback.llm_client import JourneybackLLMClient, LLMResponseError  # noqa: E402


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}


class RecordingClient(JourneybackLLMClient):
    def __init__(self, settings: LLMSettings, *, output: dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self.output = output or {"summary": "structured result"}
        self.calls: list[dict[str, Any]] = []

    def _post(
        self,
        *,
        api_base: str,
        api_key: str,
        path: str,
        payload: dict[str, Any],
        provider: str,
    ) -> dict[str, Any]:
        self.calls.append({
            "api_base": api_base,
            "api_key": api_key,
            "path": path,
            "payload": payload,
            "provider": provider,
        })
        if path == "/embeddings":
            return {"data": [{"index": 0, "embedding": [0.2, 0.8]}]}
        return {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(self.output)},
            }]
        }


class LLMSettingsTests(unittest.TestCase):
    def test_hybrid_env_uses_deepseek_and_siliconflow_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text(
                "\n".join([
                    "DEEPSEEK_API_KEY=ds-test-key",
                    "DEEPSEEK_BASE_URL=https://api.deepseek.com",
                    "JOURNEYBACK_LLM_PROVIDER=deepseek",
                    "JOURNEYBACK_LLM_MODEL=deepseek-v4-flash",
                    "SILICONFLOW_API_KEY=siliconflow-test-key",
                    "SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1",
                    "JOURNEYBACK_EMBEDDING_PROVIDER=siliconflow",
                    "JOURNEYBACK_EMBEDDING_MODEL=BAAI/bge-m3",
                ]),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = LLMSettings.from_env(env_file)

        self.assertTrue(settings.configured)
        self.assertEqual("ds-test-key", settings.llm_api_key)
        self.assertEqual("siliconflow-test-key", settings.embedding_api_key)
        self.assertNotIn("api_key", settings.public_summary())
        self.assertNotIn("ds-test-key", json.dumps(settings.public_summary()))
        self.assertNotIn("siliconflow-test-key", json.dumps(settings.public_summary()))

    def test_placeholder_keys_are_not_treated_as_configured(self) -> None:
        settings = LLMSettings(
            llm_api_key="replace-with-your-deepseek-api-key",
            embedding_api_key="replace-with-your-siliconflow-api-key",
        )
        self.assertFalse(settings.configured)


class JourneybackLLMClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = LLMSettings(
            model="deepseek-v4-flash",
            embedding_model="BAAI/bge-m3",
            llm_provider="deepseek",
            llm_api_key="ds-test-key",
            llm_api_base="https://api.deepseek.com",
            embedding_provider="siliconflow",
            embedding_api_key="siliconflow-test-key",
            embedding_api_base="https://api.siliconflow.cn/v1",
        )

    def test_routes_generation_to_deepseek_and_embeddings_to_siliconflow(self) -> None:
        client = RecordingClient(self.settings)
        result = client.structured(
            instructions="Return incident facts.",
            input_text="A checked bag is delayed.",
            schema_name="incident",
            schema=SCHEMA,
        )
        embeddings = client.embed(["baggage delay"])

        self.assertEqual({"summary": "structured result"}, result)
        self.assertEqual([[0.2, 0.8]], embeddings)
        self.assertEqual("/chat/completions", client.calls[0]["path"])
        self.assertEqual("ds-test-key", client.calls[0]["api_key"])
        self.assertEqual({"type": "json_object"}, client.calls[0]["payload"]["response_format"])
        self.assertEqual({"type": "disabled"}, client.calls[0]["payload"]["thinking"])
        self.assertIn("JSON", client.calls[0]["payload"]["messages"][0]["content"])
        self.assertEqual("/embeddings", client.calls[1]["path"])
        self.assertEqual("https://api.siliconflow.cn/v1", client.calls[1]["api_base"])
        self.assertEqual("siliconflow-test-key", client.calls[1]["api_key"])
        self.assertEqual("BAAI/bge-m3", client.calls[1]["payload"]["model"])

    def test_rejects_json_that_does_not_match_schema(self) -> None:
        client = RecordingClient(self.settings, output={"wrong": "field"})
        with self.assertRaises(LLMResponseError):
            client.structured(
                instructions="Return incident facts.",
                input_text="A checked bag is delayed.",
                schema_name="incident",
                schema=SCHEMA,
            )


if __name__ == "__main__":
    unittest.main()
