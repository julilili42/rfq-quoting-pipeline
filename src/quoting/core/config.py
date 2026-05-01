"""Central runtime configuration loaded from environment variables.

Naming
------
This module owns *runtime* / *environment* settings — LLM provider keys,
data directories, thresholds, etc. The prefered public name is
:func:`load_runtime_settings`. ``load_settings`` is kept as an alias
for back-compatibility; new code should use the explicit name to
disambiguate from :func:`quoting.api.settings_store.load_user_settings`,
which deals with persisted UI preferences.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

Provider = Literal["gemini", "azure"]

# Project root = three levels up from this file:
#   src/quoting/core/config.py -> core -> quoting -> src -> <root>
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    # LLM
    llm_provider: Provider = "gemini"
    llm_max_retries: int = 3
    llm_timeout_s: int = 120

    # Gemini
    google_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    # Azure OpenAI / Nexus
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
    #
    # The DPI is what the LLM "sees" for vision-based extraction. 200 DPI
    # was overkill for typical RFQs — most are clean digital PDFs where
    # 150 DPI is plenty for the model to read every digit and matrix
    # correctly, while shrinking the upload payload by ~44 %. Faster
    # network round trip and faster vision processing on the provider
    # side. For scans the user can override via PDF_RENDER_DPI in .env.
    pdf_render_dpi: int = 150

    @property
    def stammdaten_path(self) -> Path:
        canonical = self.data_dir / "stammdaten.csv"
        if canonical.exists():
            return canonical
        legacy = self.data_dir / "stammdaten_test.csv"
        if legacy.exists():
            return legacy
        return canonical

    @property
    def preise_path(self) -> Path:
        return self.data_dir / "preise.csv"


def load_runtime_settings() -> Settings:
    """Build :class:`Settings` from environment. No side effects.

    This is the canonical name for runtime/env-driven configuration.
    """
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
        pdf_render_dpi=_int("PDF_RENDER_DPI", base.pdf_render_dpi),
    )


# Back-compat alias. Prefer :func:`load_runtime_settings` in new code.
load_settings = load_runtime_settings
