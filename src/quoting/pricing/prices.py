"""External price-override table loading."""
from __future__ import annotations

import csv
from pathlib import Path

from ..core import get_logger

log = get_logger()


def load_prices(path: Path) -> dict[str, dict[str, float]]:
    """Load external price overrides. Returns {artikel_nr: {basispreis, zkalk_offset}}."""
    if not path.exists():
        return {}

    prices: dict[str, dict[str, float]] = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                prices[row["artikel_nr"]] = {
                    "basispreis": float(row.get("basispreis_eur", 0) or 0),
                    "zkalk_offset": float(row.get("zkalk_offset_eur", 0) or 0),
                }
            except ValueError as e:
                log.warning("Skipping malformed price row %s: %s", row, e)
    return prices
