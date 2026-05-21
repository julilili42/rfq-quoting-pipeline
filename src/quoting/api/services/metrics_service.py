"""Aggregate review-level metrics for the dashboard from SQLite."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from quoting.api import _common
from quoting.reviews.summary import ReviewSummary, scan_reviews


def _progress_summary(progress: dict | None) -> dict:
    if not isinstance(progress, dict):
        return {}
    result = progress.get("result")
    if not isinstance(result, dict):
        return {}
    summary = result.get("summary")
    return summary if isinstance(summary, dict) else {}


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _active_step_duration_from_progress(progress: dict | None) -> float:
    if not isinstance(progress, dict):
        return 0.0
    steps = progress.get("steps")
    if not isinstance(steps, list):
        return 0.0

    duration_s = 0.0
    for step in steps:
        if not isinstance(step, dict):
            continue
        started_at = _parse_datetime(step.get("started_at"))
        completed_at = _parse_datetime(step.get("completed_at"))
        if started_at is None or completed_at is None:
            continue
        duration_s += max((completed_at - started_at).total_seconds(), 0.0)

    return duration_s


def _duration_from_progress(progress: dict | None, summary: dict) -> float:
    active_duration = _active_step_duration_from_progress(progress)
    if active_duration > 0:
        return active_duration

    duration = float(summary.get("duration_s") or 0.0)
    if duration > 0:
        return duration
    if not isinstance(progress, dict) or progress.get("status") != "completed":
        return 0.0
    started_at = _parse_datetime(progress.get("created_at"))
    completed_at = _parse_datetime(progress.get("updated_at"))
    if started_at is None or completed_at is None:
        return 0.0
    return max((completed_at - started_at).total_seconds(), 0.0)


def _duration_from_completed_jobs(repo: Any, review_id: str) -> float:
    with repo.connect() as conn:
        rows = conn.execute(
            """
            SELECT claimed_at, completed_at
            FROM jobs
            WHERE review_id = ?
              AND status = 'completed'
              AND claimed_at IS NOT NULL
              AND completed_at IS NOT NULL
            """,
            (review_id,),
        ).fetchall()

    duration_s = 0.0
    for row in rows:
        started_at = _parse_datetime(row["claimed_at"])
        completed_at = _parse_datetime(row["completed_at"])
        if started_at is None or completed_at is None:
            continue
        duration_s += max((completed_at - started_at).total_seconds(), 0.0)

    return duration_s


def _approval_duration(summary: ReviewSummary, approval: dict | None) -> tuple[float, str | None]:
    if not isinstance(approval, dict):
        return 0.0, None

    approved_at_raw = approval.get("approved_at")
    approved_at = _parse_datetime(approved_at_raw)
    created_at = _parse_datetime(summary.created_at)
    if approved_at is None or created_at is None:
        return 0.0, approved_at_raw if isinstance(approved_at_raw, str) else None

    return (
        max((approved_at - created_at).total_seconds(), 0.0),
        approved_at.isoformat(),
    )


def _is_completed(summary: ReviewSummary, progress: dict | None) -> bool:
    if isinstance(progress, dict) and progress.get("status") == "completed":
        return True
    return summary.status in {"abgeschlossen", "pdf_bereit"}


def _token_usage_from_payload(payload: dict | None, fallback_summary: dict) -> dict | None:
    if isinstance(payload, dict):
        totals = payload.get("totals")
        calls = payload.get("calls")
        if isinstance(totals, dict) and isinstance(calls, list) and calls:
            return {
                "input_tokens": int(totals.get("input_tokens") or 0),
                "output_tokens": int(totals.get("output_tokens") or 0),
                "total_tokens": int(totals.get("total_tokens") or 0),
            }

    token_data = fallback_summary.get("token_usage")
    if isinstance(token_data, dict):
        return {
            "input_tokens": int(token_data.get("input_tokens") or 0),
            "output_tokens": int(token_data.get("output_tokens") or 0),
            "total_tokens": int(token_data.get("total_tokens") or 0),
        }
    return None


def _has_llm_extraction(payload: dict | None, progress_summary: dict) -> bool:
    extraction_path = progress_summary.get("extraction_path")
    if extraction_path == "llm":
        return True
    if not isinstance(payload, dict):
        return False
    calls = payload.get("calls")
    if not isinstance(calls, list):
        return False
    return any(isinstance(call, dict) and call.get("source") == "extraction" for call in calls)


def _resolve_extraction_path(
    *,
    summary: ReviewSummary,
    progress: dict | None,
    progress_summary: dict,
    llm_usage: dict | None,
    extraction_meta: dict | None,
    token_row: dict | None,
) -> str | None:
    if isinstance(extraction_meta, dict):
        path = extraction_meta.get("path")
        if path in {"fast_path", "llm"}:
            return str(path)

    path = progress_summary.get("extraction_path")
    if path in {"fast_path", "llm"}:
        return str(path)

    if _has_llm_extraction(llm_usage, progress_summary):
        return "llm"

    # Legacy fallback: older completed fast-path reviews have extracted
    # positions but no persisted path and no LLM token payload.
    if (
        token_row is None
        and summary.positions > 0
        and _is_completed(summary, progress)
    ):
        return "fast_path"

    return None


def _accumulate_review_into(
    summary: ReviewSummary,
    progress: dict | None,
    llm_usage: dict | None,
    extraction_meta: dict | None,
    approval: dict | None,
    job_duration_s: float,
    agg: dict,
    per_review: list,
) -> None:
    """Accumulate one review's metrics into agg and append a row to per_review."""
    agg["total_reviews"] += 1
    if _is_completed(summary, progress):
        agg["completed_reviews"] += 1

    progress_summary = _progress_summary(progress)
    positions = summary.positions
    total_eur = summary.total_eur
    duration_s = job_duration_s or _duration_from_progress(progress, progress_summary)
    approval_duration_s, approved_at = _approval_duration(summary, approval)
    match_rate = summary.match_rate

    agg["total_positions"] += positions
    agg["total_eur"] += total_eur
    if duration_s:
        agg["sum_duration_s"] += duration_s
        agg["reviews_with_duration"] += 1
    if approval_duration_s:
        agg["sum_approval_duration_s"] += approval_duration_s
        agg["reviews_with_approval_duration"] += 1
    if positions:
        agg["sum_match_rate"] += match_rate
        agg["reviews_with_match"] += 1

    token_row = _token_usage_from_payload(llm_usage, progress_summary)
    if token_row is not None:
        agg["total_input_tokens"] += token_row["input_tokens"]
        agg["total_output_tokens"] += token_row["output_tokens"]
        agg["total_tokens"] += token_row["total_tokens"]
        agg["reviews_with_token_data"] += 1

    extraction_path = _resolve_extraction_path(
        summary=summary,
        progress=progress,
        progress_summary=progress_summary,
        llm_usage=llm_usage,
        extraction_meta=extraction_meta,
        token_row=token_row,
    )
    if extraction_path == "fast_path":
        agg["fast_path_hits"] += 1
    elif extraction_path == "llm":
        agg["llm_calls"] += 1

    per_review.append({
        "review_id": summary.review_id,
        "subject": summary.subject,
        "status": progress.get("status") if isinstance(progress, dict) else summary.status,
        "updated_at": (
            str(progress.get("updated_at") or "")
            if isinstance(progress, dict)
            else summary.updated_at.isoformat()
        ),
        "positions": positions,
        "match_rate": round(match_rate, 3),
        "total_eur": total_eur,
        "duration_s": duration_s,
        "approval_duration_s": approval_duration_s,
        "approved_at": approved_at,
        "token_usage": token_row,
        "extraction_path": extraction_path,
    })


def compute_metrics() -> dict:
    repo = _common.get_review_repo()
    summaries = scan_reviews(repo=repo)
    per_review: list[dict] = []
    agg: dict = dict(
        total_reviews=0, completed_reviews=0, total_positions=0,
        total_eur=0.0, sum_duration_s=0.0, sum_match_rate=0.0,
        sum_approval_duration_s=0.0,
        reviews_with_duration=0, reviews_with_match=0,
        reviews_with_approval_duration=0,
        total_input_tokens=0, total_output_tokens=0, total_tokens=0,
        reviews_with_token_data=0,
        fast_path_hits=0, llm_calls=0,
    )

    for summary in summaries:
        progress = repo.load_progress(summary.review_id)
        llm_usage = repo.load_llm_usage(summary.review_id)
        extraction_meta = repo.load_extraction_meta(summary.review_id)
        approval = repo.load_approval(summary.review_id)
        _accumulate_review_into(
            summary,
            progress,
            llm_usage,
            extraction_meta,
            approval,
            _duration_from_completed_jobs(repo, summary.review_id),
            agg,
            per_review,
        )

    reviews_with_duration = agg.pop("reviews_with_duration") or 1
    reviews_with_match = agg.pop("reviews_with_match") or 1
    reviews_with_approval_duration = agg.pop("reviews_with_approval_duration")
    sum_duration_s = agg.pop("sum_duration_s")
    sum_match_rate = agg.pop("sum_match_rate")
    sum_approval_duration_s = agg.pop("sum_approval_duration_s")

    return {
        **agg,
        "avg_duration_s": round(sum_duration_s / reviews_with_duration, 2),
        "avg_approval_duration_s": (
            round(sum_approval_duration_s / reviews_with_approval_duration, 2)
            if reviews_with_approval_duration
            else 0.0
        ),
        "reviews_with_approval_duration": reviews_with_approval_duration,
        "avg_match_rate": round(sum_match_rate / reviews_with_match, 3),
        "per_review": per_review,
    }
