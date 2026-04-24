"""Volume discount tiers and logic."""
from __future__ import annotations

# (min_qty, discount fraction). Ordered high -> low so first match wins.
_VOLUME_TIERS: list[tuple[float, float]] = [
    (1000, 0.15),
    (500, 0.10),
    (100, 0.05),
]


def volume_discount(qty: float) -> float:
    """Return discount fraction (0.10 = 10%) based on quantity tiers."""
    for threshold, discount in _VOLUME_TIERS:
        if qty >= threshold:
            return discount
    return 0.0
