"""Build ``data/stammdaten.csv`` from the historical offer export.

The source ``Overview_Offers.xlsx`` is an export of all sales offers from
the SAP / quoting backend. It contains one row per offer-position. For
quoting we want the *opposite*: one row per article number, with the
typical sales price aggregated across history.

This script is the prototype's stand-in for a proper SAP / SQL pipeline
— run it once whenever the source export changes; the rest of the code
just consumes ``stammdaten.csv``.

Usage::

    python -m quoting.data.prep.build_stammdaten \
        data/raw/Overview_Offers.xlsx \
        --output data/stammdaten.csv

The same logic is exposed as :func:`build_stammdaten_csv` so other tools
(notebooks, tests) can call it directly.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Generic placeholder article numbers used by the source system for
# free-text / unspecified items. They carry no real article identity and
# are excluded from the master data.
_GENERIC_ARTICLE_PREFIXES = ("00000000",)
_GENERIC_ARTICLE_INFIXES = ("YY",)
_GENERIC_ZZ_TAIL = "ZZ0000"
_GENERIC_ZZ_HEAD = "00009"

# Materials worth recognising in free-text descriptions. Order matters:
# longer / more specific names first, so "PA66" is matched before "PA".
_MATERIAL_TOKENS: tuple[str, ...] = (
    "PCTFE", "PVDF", "PEEK", "PTFE", "PA66", "PA12", "PA6", "POM",
    "FFKM", "FKM", "EPDM", "ETFE", "PFA", "FEP", "NBR",
    "HDPE", "LDPE", "EVA", "PP", "PE",
    "GRAPHIT", "KOHLE",
)

# Pattern that grabs dimension strings like ``108x15``, ``3000(±20)X1000(±20)X12``
# or ``Ø7 x 1000``. Tolerances in parentheses are stripped from the
# captured value so we end up with a clean ``3000X1000X12``.
_DIMENSION_RE = re.compile(
    r"(?:Ø\s*)?\d+(?:[,.]\d+)?(?:\([^)]+\))?"
    r"\s*(?:[xX×])\s*\d+(?:[,.]\d+)?(?:\([^)]+\))?"
    r"(?:\s*(?:[xX×])\s*\d+(?:[,.]\d+)?(?:\([^)]+\))?)*"
)
_DN_RE = re.compile(r"\bDN\s*\d+", re.IGNORECASE)


@dataclass(frozen=True)
class BuildStats:
    """Lightweight summary of a build run."""

    rows_in: int
    rows_out: int
    rows_dropped_generic: int
    rows_dropped_currency: int


# --------------------------------------------------------------------- helpers


def _is_generic_article(art: object) -> bool:
    """True for placeholder article numbers (no real identity)."""
    if not isinstance(art, str):
        return True
    if any(art.startswith(p) for p in _GENERIC_ARTICLE_PREFIXES):
        return True
    if any(infix in art for infix in _GENERIC_ARTICLE_INFIXES):
        return True
    if art.startswith(_GENERIC_ZZ_HEAD) and art.endswith(_GENERIC_ZZ_TAIL):
        return True
    return False


def _parse_material(bezeichnung: object) -> str | None:
    """Pull recognised material tokens out of a free-text description."""
    if not isinstance(bezeichnung, str):
        return None
    upper = bezeichnung.upper()
    found: list[str] = []
    for token in _MATERIAL_TOKENS:
        if re.search(r"\b" + re.escape(token) + r"\b", upper) and token not in found:
            found.append(token)
    return ", ".join(found) if found else None


def _parse_dimensions(bezeichnung: object) -> str | None:
    """Pull a dimension string (``"108x15"``, ``"DN50"``) from free text."""
    if not isinstance(bezeichnung, str):
        return None
    match = _DIMENSION_RE.search(bezeichnung)
    if match:
        cleaned = re.sub(r"\([^)]+\)", "", match.group(0))
        return re.sub(r"\s+", "", cleaned)
    match = _DN_RE.search(bezeichnung)
    return match.group(0) if match else None


def _mode_or_first(series):
    """Most common non-null value, falling back to first observation."""
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    mode = cleaned.mode()
    if not mode.empty:
        return mode.iat[0]
    return cleaned.iloc[0]


# ---------------------------------------------------------------------- public


def build_stammdaten_csv(
    source_xlsx: Path,
    output_csv: Path,
    *,
    sheet_name: str | int = 0,
    only_currency: str = "EUR",
) -> BuildStats:
    """Convert an Overview-Offers export into a clean stammdaten CSV.

    Parameters
    ----------
    source_xlsx
        Path to the offer-history export.
    output_csv
        Destination CSV. Parent directory is created if needed.
    sheet_name
        Excel sheet to read. Defaults to the first sheet.
    only_currency
        Limit to rows in this currency so price aggregations stay
        comparable. Pass ``""`` to keep every row.
    """
    # ``pandas`` is a heavy dependency we only need for the offline build,
    # so it's imported lazily.
    import pandas as pd  # noqa: PLC0415

    source_xlsx = Path(source_xlsx)
    output_csv = Path(output_csv)

    df = pd.read_excel(source_xlsx, sheet_name=sheet_name)
    rows_in = len(df)

    df = df.rename(
        columns={
            "E~Material":     "artikel_nr",
            "E~Bezeichng.":   "bezeichnung",
            "E~Nettopreis":   "_nettopreis",
            "E~Einheit":      "_pe",        # price-per quantity (1 / 100 / ...)
            "E~Einheit.1":    "_einheit",   # ST, M, KG, ...
            "E~Währung":      "_waehrung",
            "F~Bezeichn.":    "_sales_group",
            "G~Bezeichn.":    "_material_group",
        }
    )

    is_generic = df["artikel_nr"].apply(_is_generic_article)
    rows_dropped_generic = int(is_generic.sum())
    df = df[~is_generic].copy()

    if only_currency:
        currency_mask = df["_waehrung"] == only_currency
        rows_dropped_currency = int((~currency_mask).sum())
        df = df[currency_mask].copy()
    else:
        rows_dropped_currency = 0

    # SAP encodes "price per N pieces" via the ``E~Einheit`` column. We
    # normalise everything to "price per single piece" so downstream
    # consumers can treat ``basispreis_eur`` as a unit price.
    pe = df["_pe"].replace(0, 1).fillna(1)
    df["_price_per_piece"] = df["_nettopreis"] / pe

    grouped = (
        df.groupby("artikel_nr", as_index=False)
        .agg(
            bezeichnung=("bezeichnung", _mode_or_first),
            basispreis_eur=("_price_per_piece", "median"),
            preis_min_eur=("_price_per_piece", "min"),
            preis_max_eur=("_price_per_piece", "max"),
            einheit=("_einheit", _mode_or_first),
            sales_group=("_sales_group", _mode_or_first),
            material_group=("_material_group", _mode_or_first),
            n_offers=("artikel_nr", "count"),
        )
    )

    grouped["werkstoff"] = grouped["bezeichnung"].apply(_parse_material)
    grouped["abmessungen"] = grouped["bezeichnung"].apply(_parse_dimensions)
    grouped["zkalk_offset_eur"] = 0.0

    grouped["einheit"] = grouped["einheit"].fillna("ST").astype(str).str.strip()
    grouped["bezeichnung"] = grouped["bezeichnung"].fillna("").astype(str).str.strip()
    for column in ("basispreis_eur", "preis_min_eur", "preis_max_eur", "zkalk_offset_eur"):
        grouped[column] = grouped[column].astype(float).round(4)

    column_order = [
        "artikel_nr",
        "bezeichnung",
        "werkstoff",
        "abmessungen",
        "einheit",
        "basispreis_eur",
        "zkalk_offset_eur",
        "preis_min_eur",
        "preis_max_eur",
        "sales_group",
        "material_group",
        "n_offers",
    ]
    grouped = grouped[column_order].sort_values("artikel_nr").reset_index(drop=True)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    grouped.to_csv(output_csv, index=False, encoding="utf-8")

    return BuildStats(
        rows_in=rows_in,
        rows_out=len(grouped),
        rows_dropped_generic=rows_dropped_generic,
        rows_dropped_currency=rows_dropped_currency,
    )


# ------------------------------------------------------------------------ CLI


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="quoting.data.prep.build_stammdaten",
        description="Build data/stammdaten.csv from an Overview-Offers export.",
    )
    parser.add_argument("source", help="Path to Overview_Offers.xlsx")
    parser.add_argument(
        "-o",
        "--output",
        default="data/stammdaten.csv",
        help="Destination CSV (default: data/stammdaten.csv)",
    )
    parser.add_argument(
        "--sheet",
        default=0,
        help="Excel sheet name or index to read (default: first sheet)",
    )
    parser.add_argument(
        "--currency",
        default="EUR",
        help="Limit rows to this currency code (default: EUR; pass empty to disable)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source = Path(args.source)
    if not source.exists():
        print(f"error: source file not found: {source}", file=sys.stderr)
        return 2

    sheet: str | int
    try:
        sheet = int(args.sheet)
    except (TypeError, ValueError):
        sheet = str(args.sheet)

    stats = build_stammdaten_csv(
        source,
        Path(args.output),
        sheet_name=sheet,
        only_currency=args.currency or "",
    )
    print(
        f"built {args.output}: "
        f"{stats.rows_out} articles "
        f"(from {stats.rows_in} offer rows, "
        f"dropped {stats.rows_dropped_generic} generic, "
        f"{stats.rows_dropped_currency} non-{args.currency or 'currency'})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
