"""Central configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Provider = Literal["gemini", "azure"]

# Project root = three levels up from this file:
# src/quoting/core/config.py -> src/quoting/core -> src/quoting -> src -> <root>
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    # LLM
    llm_provider: Provider = "gemini"
    llm_max_retries: int = 3
    llm_timeout_s: int = 120

    # Gemini
    google_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    # Azure OpenAI (Nexus)
    nexus_api_key: str | None = None
    azure_endpoint: str = "https://genai-nexus.api.corpinter.net/"
    azure_api_version: str = "2024-10-21"
    azure_model: str = "gpt-5-mini"

    # Paths
    project_root: Path = field(default_factory=lambda: _PROJECT_ROOT)
    data_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "data")
    output_dir: Path = field(default_factory=lambda: Path(r"C:\Business & AI\Output"))

    # Matching
    fuzzy_threshold: int = 85
    semantic_threshold: int = 70

    # PDF rendering
    pdf_render_dpi: int = 200

    @property
    def stammdaten_path(self) -> Path:
        return self.data_dir / "stammdaten_test.csv"

    @property
    def preise_path(self) -> Path:
        return self.data_dir / "preise.csv"


def load_settings() -> Settings:
    """Build Settings from environment. No side effects."""
    def _int(key: str, default: int) -> int:
        try:
            return int(os.getenv(key, default))
        except ValueError:
            return default

    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider not in ("gemini", "azure"):
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")

    output = os.getenv("OUTPUT_DIR")
    data = os.getenv("DATA_DIR")

    base = Settings()
    return Settings(
        llm_provider=provider,  # type: ignore[arg-type]
        llm_max_retries=_int("LLM_MAX_RETRIES", 3),
        llm_timeout_s=_int("LLM_TIMEOUT_S", 120),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        nexus_api_key=os.getenv("NEXUS_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", base.azure_endpoint),
        azure_api_version=os.getenv("AZURE_OPENAI_API_VERSION", base.azure_api_version),
        azure_model=os.getenv("AZURE_OPENAI_MODEL", base.azure_model),
        output_dir=Path(output) if output else base.output_dir,
        data_dir=Path(data) if data else base.data_dir,
        fuzzy_threshold=_int("FUZZY_THRESHOLD", 85),
        semantic_threshold=_int("SEMANTIC_THRESHOLD", 70),
        pdf_render_dpi=_int("PDF_RENDER_DPI", 200),
    )
