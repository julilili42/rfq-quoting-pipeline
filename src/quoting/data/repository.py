"""Stammdaten access layer.

The rest of the codebase only ever talks to the master data through a
:class:`StammdatenRepository`. The repository is a thin protocol so a
production install can swap the local CSV out for SQL, SAP, or an HTTP
service without anyone else noticing.

Public surface
--------------

* :class:`StammdatenRepository` — Protocol describing the boundary.
* :class:`CsvStammdatenRepository` — default implementation, backed by
  ``data/stammdaten.csv``.
* :class:`InMemoryStammdatenRepository` — simple constructor-injected
  store; useful for tests.
* :func:`build_repository` — picks the right implementation for a path
  (or falls back to a small mock dataset when the file is missing).
"""

from __future__ import annotations

import csv
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..core import get_logger
from .records import StammdatenRecord

log = get_logger()


@runtime_checkable
class StammdatenRepository(Protocol):
    """Read-only access to the article master data.

    Implementations should be cheap to construct; loading happens
    lazily on first call. Subsequent calls hit a cache.
    """

    def all(self) -> list[StammdatenRecord]:
        """Return every record. Stable ordering is not guaranteed."""

    def by_artikelnr(self, artikel_nr: str) -> StammdatenRecord | None:
        """Look up a single record by exact article number."""

    def as_rows(self) -> list[dict]:
        """Return every record in the legacy ``list[dict]`` shape.

        Provided so existing dict-based consumers (the matcher, the
        pricing module) keep working unchanged.
        """


# ---------------------------------------------------------------- CSV backend


class CsvStammdatenRepository:
    """Default repository: read articles from a CSV file.

    The CSV is expected to be UTF-8 with a header row. Required columns
    are ``artikel_nr`` and ``bezeichnung``; everything else is
    best-effort. The expected schema matches what
    :mod:`quoting.data.prep.build_stammdaten` produces.
    """

    REQUIRED_COLUMNS = frozenset({"artikel_nr", "bezeichnung"})

    def __init__(self, path: Path):
        self._path = Path(path)
        self._records: list[StammdatenRecord] | None = None
        self._index: dict[str, StammdatenRecord] = {}

    @property
    def path(self) -> Path:
        return self._path

    # -------------------------------------------- StammdatenRepository

    def all(self) -> list[StammdatenRecord]:
        if self._records is None:
            self._records = self._load()
            self._index = {r.artikel_nr: r for r in self._records}
        return self._records

    def by_artikelnr(self, artikel_nr: str) -> StammdatenRecord | None:
        if self._records is None:
            self.all()
        return self._index.get(artikel_nr)

    def as_rows(self) -> list[dict]:
        return [r.to_row() for r in self.all()]

    # -------------------------------------------------------- internal

    def _load(self) -> list[StammdatenRecord]:
        with open(self._path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            missing = self.REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"Stammdaten {self._path} is missing required columns: {sorted(missing)}"
                )
            records = [_record_from_row(row) for row in reader]
        log.info("Loaded %d stammdaten record(s) from %s", len(records), self._path.name)
        return records


# ------------------------------------------------------------ in-memory backend


class InMemoryStammdatenRepository:
    """Repository backed by an explicit list of records.

    Useful for tests and for future implementations that build records
    in memory (e.g. an SAP adapter that pages through API results).
    """

    def __init__(self, records: Iterable[StammdatenRecord]):
        self._records = list(records)
        self._index = {r.artikel_nr: r for r in self._records}

    def all(self) -> list[StammdatenRecord]:
        return list(self._records)

    def by_artikelnr(self, artikel_nr: str) -> StammdatenRecord | None:
        return self._index.get(artikel_nr)

    def as_rows(self) -> list[dict]:
        return [r.to_row() for r in self._records]


# --------------------------------------------------------------------- factory


def build_repository(path: Path | None = None) -> StammdatenRepository:
    """Pick a repository for a given stammdaten path.

    If ``path`` is missing on disk we fall back to a small mock dataset
    so demos and tests keep running. Production-like environments fail
    loudly instead of silently quoting against mock master data.
    """
    if path is not None and Path(path).exists():
        return CsvStammdatenRepository(Path(path))

    if _requires_real_stammdaten():
        location = str(path) if path is not None else "no path configured"
        raise FileNotFoundError(
            f"Stammdaten required in production mode, but not found: {location}"
        )

    if path is not None:
        log.warning("Stammdaten not found at %s, using mock data", path)
    return InMemoryStammdatenRepository(_mock_records())


# ------------------------------------------------------------------- internals


def _record_from_row(row: dict) -> StammdatenRecord:
    """Coerce a raw CSV row into a typed record."""
    return StammdatenRecord(
        artikel_nr=str(row.get("artikel_nr") or "").strip(),
        bezeichnung=str(row.get("bezeichnung") or "").strip(),
        werkstoff=_optional_str(row.get("werkstoff")),
        abmessungen=_optional_str(row.get("abmessungen")),
        einheit=str(row.get("einheit") or "ST").strip() or "ST",
        basispreis_eur=_required_float(row.get("basispreis_eur"), default=0.0),
        zkalk_offset_eur=_required_float(row.get("zkalk_offset_eur"), default=0.0),
        preis_min_eur=_optional_float(row.get("preis_min_eur")),
        preis_max_eur=_optional_float(row.get("preis_max_eur")),
        sales_group=_optional_str(row.get("sales_group")),
        material_group=_optional_str(row.get("material_group")),
        n_offers=_required_int(row.get("n_offers"), default=0),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _optional_float(value: object, *, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if result != result:  # NaN check without importing math
        return default
    return result


def _required_float(value: object, *, default: float) -> float:
    """Like :func:`_optional_float` but with a non-optional ``default``."""
    parsed = _optional_float(value, default=default)
    return parsed if parsed is not None else default


def _optional_int(value: object, *, default: int | None = None) -> int | None:
    raw = _optional_float(value)
    if raw is None:
        return default
    return int(raw)


def _required_int(value: object, *, default: int) -> int:
    parsed = _optional_int(value, default=default)
    return parsed if parsed is not None else default


def _requires_real_stammdaten() -> bool:
    if _env_truthy(os.getenv("QUOTING_REQUIRE_STAMMDATEN")):
        return True

    env = (
        os.getenv("QUOTING_ENV")
        or os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("ENV")
        or ""
    ).strip().lower()
    return env in {"prod", "production"}


def _env_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _mock_records() -> list[StammdatenRecord]:
    """Tiny dataset preserved for offline demos / smoke tests."""
    return [
        StammdatenRecord(
            artikel_nr="001GLP108015",
            bezeichnung="Gleitstück für Wiegenträger PTFE/Graphit 108x15",
            werkstoff="PTFE mit 15% Graphit",
            abmessungen="108x15",
            einheit="ST",
            basispreis_eur=24.50,
            zkalk_offset_eur=1.20,
        ),
        StammdatenRecord(
            artikel_nr="002GLS082003",
            bezeichnung="Gleitstück für Wiegenträger variabler Werkstoff 108x15",
            werkstoff="PTFE (diverse Compound-Optionen)",
            abmessungen="108x15",
            einheit="ST",
            basispreis_eur=28.75,
            zkalk_offset_eur=1.80,
        ),
        StammdatenRecord(
            artikel_nr="001APZ00031B",
            bezeichnung="Abnahmeprüfzeugnis DIN EN 10204:2005-01 3.1",
            werkstoff=None,
            einheit="ST",
            basispreis_eur=45.00,
            zkalk_offset_eur=0.0,
        ),
    ]
