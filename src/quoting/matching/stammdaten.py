"""Master-data loading.

Historically this module owned both file I/O and the dict shape passed
to the matcher. Both responsibilities now live in
:mod:`quoting.data`. The function below is a thin convenience wrapper
preserved so existing callers (``quoting.pipeline.orchestrator``,
tests, scripts) keep working unchanged.

New code should depend on :class:`quoting.data.StammdatenRepository`
directly.
"""

from __future__ import annotations

from pathlib import Path

from ..data import build_repository


def load_stammdaten(path: Path) -> list[dict]:
    """Return master data as ``list[dict]``.

    Falls back to the repository's mock dataset when ``path`` does not
    exist on disk. The dict shape matches what the matcher and pricing
    modules already consume (``artikel_nr``, ``bezeichnung``,
    ``werkstoff``, ``basispreis_eur``, ``zkalk_offset_eur``, …).
    """
    return build_repository(path).as_rows()
