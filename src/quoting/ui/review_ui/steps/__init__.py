"""Per-step renderers for the review-detail page.

Each step is a small module exposing a ``render(review_input, anfrage,
matches)`` function. ``main.py`` picks the right one based on the
current ``active_step`` query param.
"""
from .approval_step import render_approval_step
from .customer_step import render_customer_step
from .positions_step import render_positions_step

__all__ = [
    "render_positions_step",
    "render_customer_step",
    "render_approval_step",
]
