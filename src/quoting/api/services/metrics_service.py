"""Aggregate review-level metrics for the dashboard from SQLite."""

from __future__ import annotations

from quoting.reviews.sqlite_repository import get_default_repository


def _extract_summary_metrics(summary: dict) -> tuple[int, float, float, float]:
    """Return (positions, total_eur, duration_s, match_rate) from a progress summary."""
    positions = int(summary.get("positions") or 0)
    total_eur = float(summary.get("total_eur") or 0.0)
    duration_s = float(summary.get("duration_s") or 0.0)
    matched = (
        int(summary.get("exact") or 0)
        + int(summary.get("fuzzy") or 0)
        + int(summary.get("semantic") or 0)
    )
    match_rate = matched / positions if positions > 0 else 0.0
    return positions, total_eur, duration_s, match_rate


def _accumulate_review_into(
    review_id: str,
    progress: dict,
    agg: dict,
    per_review: list,
) -> None:
    """Accumulate one review's metrics into agg and append a row to per_review."""
    agg["total_reviews"] += 1
    if progress.get("status") == "completed":
        agg["completed_reviews"] += 1

    summary = (progress.get("result") or {}).get("summary") or {}
    positions, total_eur, duration_s, match_rate = _extract_summary_metrics(summary)

    agg["total_positions"] += positions
    agg["total_eur"] += total_eur
    if duration_s:
        agg["sum_duration_s"] += duration_s
        agg["reviews_with_duration"] += 1
    if positions:
        agg["sum_match_rate"] += match_rate
        agg["reviews_with_match"] += 1

    token_data = summary.get("token_usage")
    token_row = None
    if isinstance(token_data, dict):
        agg["total_input_tokens"] += int(token_data.get("input_tokens") or 0)
        agg["total_output_tokens"] += int(token_data.get("output_tokens") or 0)
        agg["total_tokens"] += int(token_data.get("total_tokens") or 0)
        agg["reviews_with_token_data"] += 1
        token_row = token_data

    extraction_path = summary.get("extraction_path")
    if extraction_path == "fast_path":
        agg["fast_path_hits"] += 1
    elif extraction_path == "llm":
        agg["llm_calls"] += 1

    per_review.append({
        "review_id": review_id,
        "subject": str(summary.get("subject") or ""),
        "status": progress.get("status"),
        "updated_at": str(progress.get("updated_at") or ""),
        "positions": positions,
        "match_rate": round(match_rate, 3),
        "total_eur": total_eur,
        "duration_s": duration_s,
        "token_usage": token_row,
        "extraction_path": extraction_path,
    })


def compute_metrics() -> dict:
    repo = get_default_repository()
    per_review: list[dict] = []
    agg: dict = dict(
        total_reviews=0, completed_reviews=0, total_positions=0,
        total_eur=0.0, sum_duration_s=0.0, sum_match_rate=0.0,
        reviews_with_duration=0, reviews_with_match=0,
        total_input_tokens=0, total_output_tokens=0, total_tokens=0,
        reviews_with_token_data=0,
        fast_path_hits=0, llm_calls=0,
    )

    for row in repo.list_reviews():
        review_id = str(row["review_id"])
        progress = repo.load_progress(review_id)
        if progress is not None:
            _accumulate_review_into(review_id, progress, agg, per_review)

    reviews_with_duration = agg.pop("reviews_with_duration") or 1
    reviews_with_match = agg.pop("reviews_with_match") or 1
    sum_duration_s = agg.pop("sum_duration_s")
    sum_match_rate = agg.pop("sum_match_rate")

    return {
        **agg,
        "avg_duration_s": round(sum_duration_s / reviews_with_duration, 2),
        "avg_match_rate": round(sum_match_rate / reviews_with_match, 3),
        "per_review": per_review,
    }
