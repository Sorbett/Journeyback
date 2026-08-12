"""Runtime configuration for the LLM-first Journeyback service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


def load_env_file(path: Path = DEFAULT_ENV_FILE) -> None:
    """Load a small dotenv file without adding a third-party dependency.

    Existing process environment variables always win. The parser intentionally
    supports only the KEY=VALUE form needed by this project.
    """

    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


@dataclass(frozen=True)
class LLMSettings:
    """OpenAI-compatible endpoint and model configuration."""

    api_key: str
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-5.4-nano"
    embedding_model: str = "text-embedding-3-small"
    reasoning_effort: str = "low"
    timeout_seconds: int = 60
    retrieval_top_k: int = 8

    @classmethod
    def from_env(cls, env_file: Path = DEFAULT_ENV_FILE) -> "LLMSettings":
        load_env_file(env_file)
        timeout = _bounded_int(os.getenv("JOURNEYBACK_LLM_TIMEOUT", "60"), 10, 180, 60)
        top_k = _bounded_int(os.getenv("JOURNEYBACK_RAG_TOP_K", "8"), 3, 15, 8)
        effort = os.getenv("JOURNEYBACK_REASONING_EFFORT", "low").strip().lower()
        if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            effort = "low"
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            api_base=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
            model=os.getenv("JOURNEYBACK_LLM_MODEL", "gpt-5.4-nano").strip(),
            embedding_model=os.getenv("JOURNEYBACK_EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            reasoning_effort=effort,
            timeout_seconds=timeout,
            retrieval_top_k=top_k,
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model and self.embedding_model)

    def public_summary(self) -> dict[str, object]:
        """Return configuration metadata without ever exposing the API key."""

        return {
            "configured": self.configured,
            "api_base": self.api_base,
            "model": self.model,
            "embedding_model": self.embedding_model,
            "reasoning_effort": self.reasoning_effort,
            "retrieval_top_k": self.retrieval_top_k,
        }


def _bounded_int(value: str, minimum: int, maximum: int, fallback: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return fallback
    return min(maximum, max(minimum, parsed))
