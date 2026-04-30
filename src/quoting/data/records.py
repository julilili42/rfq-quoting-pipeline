"""Typed records for the data layer.

The rest of the application has historically dealt with stammdaten as
``list[dict]`` — flexible, but type-blind. We keep that shape on the
boundary (matcher consumers are unchanged) but introduce a real
:class:`StammdatenRecord` so the data layer itself is type-checked and
new code has something concrete to work with.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StammdatenRecord:
    """One article in the master-data table.

    Fields beyond ``artikel_nr`` and ``bezeichnung`` are best-effort:
    they're populated when the source data carries them and left empty
    otherwise. ``basispreis_eur`` is normalised to *price per single
    piece* regardless of how the source SAP system encoded it.
    """

    artikel_nr: str
    bezeichnung: str
    werkstoff: str | None = None
    abmessungen: str | None = None
    einheit: str = "ST"
    basispreis_eur: float = 0.0
    zkalk_offset_eur: float = 0.0
    preis_min_eur: float | None = None
    preis_max_eur: float | None = None
    sales_group: str | None = None
    material_group: str | None = None
    n_offers: int = 0

    def to_row(self) -> dict:
        """Return the legacy dict shape consumed by the matcher.

        Kept identical to the historical CSV columns so existing call
        sites — most importantly ``quoting.matching.matcher`` and
        ``quoting.pricing.quotation`` — keep working without changes.
        """
        return asdict(self)
