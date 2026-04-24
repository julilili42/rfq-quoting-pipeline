"""Master-data loading (stammdaten)."""
from __future__ import annotations

import csv
from pathlib import Path

from ..core import get_logger

log = get_logger()

_REQUIRED_COLS = {"artikel_nr", "bezeichnung"}


def load_stammdaten(path: Path) -> list[dict]:
    """Load master data from CSV. Falls back to mock data if file missing."""
    if not path.exists():
        log.warning("Stammdaten not found at %s, using mock data", path)
        return _mock_stammdaten()

    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = _REQUIRED_COLS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Stammdaten missing columns: {missing}")
        rows.extend(reader)
    log.info("Loaded %d master-data rows from %s", len(rows), path.name)
    return rows


def _mock_stammdaten() -> list[dict]:
    return [
        {
            "artikel_nr": "001GLP108015",
            "bezeichnung": "Gleitstück für Wiegenträger PTFE/Graphit 108x15",
            "werkstoff": "PTFE mit 15% Graphit",
            "basispreis_eur": "24.50",
            "zkalk_offset_eur": "1.20",
        },
        {
            "artikel_nr": "002GLS082003",
            "bezeichnung": "Gleitstück für Wiegenträger variabler Werkstoff 108x15",
            "werkstoff": "PTFE (diverse Compound-Optionen)",
            "basispreis_eur": "28.75",
            "zkalk_offset_eur": "1.80",
        },
        {
            "artikel_nr": "001APZ00031B",
            "bezeichnung": "Abnahmeprüfzeugnis DIN EN 10204:2005-01 3.1",
            "werkstoff": "-",
            "basispreis_eur": "45.00",
            "zkalk_offset_eur": "0.00",
        },
    ]
