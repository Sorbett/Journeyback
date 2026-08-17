"""Runtime configuration for the multi-provider Journeyback service."""

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
    """Independent text-generation and embedding provider configuration."""

    model: str = "deepseek-v4-flash"
    embedding_model: str = "BAAI/bge-m3"
    reasoning_effort: str = "low"
    timeout_seconds: int = 60
    retrieval_top_k: int = 8
    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_api_base: str = "https://api.deepseek.com"
    embedding_provider: str = "siliconflow"
    embedding_api_key: str = ""
    embedding_api_base: str = "https://api.siliconflow.cn/v1"

    @classmethod
    def from_env(cls, env_file: Path = DEFAULT_ENV_FILE) -> "LLMSettings":
        load_env_file(env_file)
        timeout = _bounded_int(os.getenv("JOURNEYBACK_LLM_TIMEOUT", "60"), 10, 180, 60)
        top_k = _bounded_int(os.getenv("JOURNEYBACK_RAG_TOP_K", "8"), 3, 15, 8)
        effort = os.getenv("JOURNEYBACK_REASONING_EFFORT", "low").strip().lower()
        if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            effort = "low"
        requested_model = os.getenv("JOURNEYBACK_LLM_MODEL", "").strip()
        requested_provider = os.getenv("JOURNEYBACK_LLM_PROVIDER", "").strip().lower()
        if requested_provider not in {"deepseek", "openai"}:
            requested_provider = (
                "deepseek"
                if os.getenv("DEEPSEEK_API_KEY", "").strip() or requested_model.startswith("deepseek-")
                else "openai"
            )
        default_model = "deepseek-v4-flash" if requested_provider == "deepseek" else "gpt-5.4-nano"
        if requested_provider == "deepseek":
            llm_api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
            llm_api_base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
        else:
            llm_api_key = os.getenv("OPENAI_API_KEY", "").strip()
            llm_api_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()

        requested_embedding_model = os.getenv("JOURNEYBACK_EMBEDDING_MODEL", "").strip()
        embedding_provider = os.getenv("JOURNEYBACK_EMBEDDING_PROVIDER", "siliconflow").strip().lower()
        if embedding_provider not in {"siliconflow", "openai"}:
            embedding_provider = "siliconflow"
        if embedding_provider == "siliconflow":
            embedding_api_key = os.getenv("SILICONFLOW_API_KEY", "").strip()
            embedding_api_base = os.getenv(
                "SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"
            ).strip()
            default_embedding_model = "BAAI/bge-m3"
        else:
            embedding_api_key = os.getenv("OPENAI_API_KEY", "").strip()
            embedding_api_base = os.getenv(
                "OPENAI_BASE_URL", "https://api.openai.com/v1"
            ).strip()
            default_embedding_model = "text-embedding-3-small"
        return cls(
            model=requested_model or default_model,
            embedding_model=requested_embedding_model or default_embedding_model,
            reasoning_effort=effort,
            timeout_seconds=timeout,
            retrieval_top_k=top_k,
            llm_provider=requested_provider,
            llm_api_key=llm_api_key,
            llm_api_base=llm_api_base.rstrip("/"),
            embedding_provider=embedding_provider,
            embedding_api_key=embedding_api_key,
            embedding_api_base=embedding_api_base.rstrip("/"),
        )

    @property
    def llm_configured(self) -> bool:
        return _usable_secret(self.llm_api_key) and bool(self.model)

    @property
    def embedding_configured(self) -> bool:
        return _usable_secret(self.embedding_api_key) and bool(self.embedding_model)

    @property
    def configured(self) -> bool:
        return self.llm_configured and self.embedding_configured

    def public_summary(self) -> dict[str, object]:
        """Return configuration metadata without ever exposing the API key."""

        return {
            "configured": self.configured,
            "llm_configured": self.llm_configured,
            "embedding_configured": self.embedding_configured,
            "llm_provider": self.llm_provider,
            "llm_api_base": self.llm_api_base,
            "embedding_provider": self.embedding_provider,
            "embedding_api_base": self.embedding_api_base,
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


def _usable_secret(value: str) -> bool:
    normalized = value.strip().lower()
    return bool(normalized) and not any(
        marker in normalized
        for marker in ("replace-with", "your-api-key", "your_", "填入", "<your")
    )
