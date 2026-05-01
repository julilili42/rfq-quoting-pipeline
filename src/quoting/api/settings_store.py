"""Persistent user / app settings.

Lives in a single JSON file under ``data/settings.json`` so it survives
restarts and can be edited by hand if needed. The Streamlit settings
page is the canonical UI; this module is the storage layer.

Naming
------
The preferred public functions are :func:`load_user_settings` and
:func:`save_user_settings`. ``load_settings`` / ``save_settings``
are kept as aliases for back-compatibility — new code should use the
explicit names to disambiguate from
:func:`quoting.core.config.load_runtime_settings`, which loads
*environment-driven runtime* configuration.

Design notes
------------
- Single global settings file (this is a single-tenant prototype).
- Defaults are merged into whatever's on disk so adding a new field
  later doesn't break existing installs.
- Atomic writes via ``.tmp`` + replace.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SETTINGS_PATH = PROJECT_ROOT / "data" / "settings.json"


@dataclass
class CompanyProfile:
    """Sender-side data that gets baked into every quotation PDF."""
    company_name: str = ""
    company_address: str = ""
    company_zip_city: str = ""
    company_country: str = "Deutschland"

    contact_person: str = ""
    contact_phone: str = ""
    contact_email: str = ""

    delivery_term: str = "EXW Werk"
    payment_term: str = "30 Tage netto"
    validity_days: int = 28


@dataclass
class MatchingPreferences:
    fuzzy_threshold: int = 85
    semantic_threshold: int = 70


@dataclass
class WorkflowPreferences:
    auto_refresh_pdf: bool = True
    confirm_before_reset: bool = True


@dataclass
class AppSettings:
    company: CompanyProfile = field(default_factory=CompanyProfile)
    matching: MatchingPreferences = field(default_factory=MatchingPreferences)
    workflow: WorkflowPreferences = field(default_factory=WorkflowPreferences)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AppSettings":
        if not isinstance(data, dict):
            return cls()
        return cls(
            company=_dataclass_from_dict(CompanyProfile, data.get("company", {})),
            matching=_dataclass_from_dict(MatchingPreferences, data.get("matching", {})),
            workflow=_dataclass_from_dict(WorkflowPreferences, data.get("workflow", {})),
        )


def _dataclass_from_dict(cls, data: dict[str, Any]):
    """Build a dataclass instance from a dict, ignoring unknown keys."""
    if not isinstance(data, dict):
        return cls()
    valid = {f.name for f in fields(cls)}
    filtered = {k: v for k, v in data.items() if k in valid}
    return cls(**filtered)


def load_user_settings() -> AppSettings:
    """Read user settings from disk, falling back to defaults."""
    if not SETTINGS_PATH.exists():
        return AppSettings()
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return AppSettings.from_dict(raw)
    except Exception:
        return AppSettings()


def save_user_settings(settings: AppSettings) -> None:
    """Atomically persist user settings."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(settings.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(SETTINGS_PATH)


# Back-compat aliases. Prefer the explicit names above in new code.
load_settings = load_user_settings
save_settings = save_user_settings
