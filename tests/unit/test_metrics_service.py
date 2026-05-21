from __future__ import annotations

from quoting.api.services.metrics_service import compute_metrics


def _seed_review(sqlite_repo, *, progress_result: dict | None = None) -> None:
    review_id = "review-1"
    sqlite_repo.create_review(
        review_id,
        subject="fallback-id",
        sender="kunde@example.com",
    )
    sqlite_repo.save_mail(
        review_id,
        {
            "subject": "Preisanfrage 2026-42",
            "from": "kunde@example.com",
            "body": "Bitte anbieten.",
        },
    )
    sqlite_repo.save_extracted(
        review_id,
        {
            "positionen": [
                {
                    "pos_nr": 1,
                    "artikelnummer": "A-1",
                    "bezeichnung": "Teil A",
                    "menge": 10,
                    "einheit": "Stk",
                    "confidence": "high",
                    "source_quote": "A-1 10 Stk",
                },
                {
                    "pos_nr": 2,
                    "artikelnummer": "B-2",
                    "bezeichnung": "Teil B",
                    "menge": 5,
                    "einheit": "Stk",
                    "confidence": "medium",
                    "source_quote": "B-2 5 Stk",
                },
            ]
        },
    )
    sqlite_repo.save_matches_initial(
        review_id,
        [
            {"pos_nr": 1, "status": "exact", "score": 1.0},
            {"pos_nr": 2, "status": "no_match", "score": 0.0},
        ],
    )
    sqlite_repo.save_quotation_initial(
        review_id,
        {"gesamtsumme": 123.45, "waehrung": "EUR"},
    )
    sqlite_repo.save_progress(
        review_id,
        {
            "review_id": review_id,
            "status": "completed",
            "created_at": "2026-05-21T10:00:00+00:00",
            "updated_at": "2026-05-21T10:00:03+00:00",
            "steps": [],
            "result": progress_result
            if progress_result is not None
            else {"review_id": review_id, "status": "completed"},
            "error": None,
        },
    )


def test_metrics_use_review_payloads_when_progress_summary_is_missing(sqlite_repo):
    _seed_review(sqlite_repo)

    metrics = compute_metrics()

    assert metrics["total_reviews"] == 1
    assert metrics["completed_reviews"] == 1
    assert metrics["total_positions"] == 2
    assert metrics["total_eur"] == 123.45
    assert metrics["avg_match_rate"] == 0.5
    assert metrics["avg_duration_s"] == 3.0
    assert metrics["per_review"][0]["subject"] == "Preisanfrage 2026-42"
    assert metrics["per_review"][0]["positions"] == 2
    assert metrics["per_review"][0]["match_rate"] == 0.5
    assert metrics["per_review"][0]["total_eur"] == 123.45


def test_metrics_keep_token_and_extraction_data_from_progress_summary(sqlite_repo):
    _seed_review(
        sqlite_repo,
        progress_result={
            "summary": {
                "duration_s": 7.25,
                "token_usage": {
                    "input_tokens": 100,
                    "output_tokens": 25,
                    "total_tokens": 125,
                },
                "extraction_path": "llm",
            }
        },
    )

    metrics = compute_metrics()

    assert metrics["avg_duration_s"] == 7.25
    assert metrics["llm_calls"] == 1
    assert metrics["fast_path_hits"] == 0
    assert metrics["total_input_tokens"] == 100
    assert metrics["total_output_tokens"] == 25
    assert metrics["total_tokens"] == 125
    assert metrics["reviews_with_token_data"] == 1
    assert metrics["per_review"][0]["token_usage"]["total_tokens"] == 125


def test_metrics_prefer_completed_job_duration_over_review_span(sqlite_repo):
    _seed_review(
        sqlite_repo,
        progress_result={"summary": {"duration_s": 20.0}},
    )
    with sqlite_repo.connect() as conn:
        conn.executemany(
            """
            INSERT INTO jobs
                (review_id, step, status, attempts, max_attempts,
                 created_at, claimed_at, completed_at)
            VALUES
                ('review-1', ?, 'completed', 1, 3, ?, ?, ?)
            """,
            [
                (
                    "extract",
                    "2026-05-21T10:00:00+00:00",
                    "2026-05-21T10:00:02+00:00",
                    "2026-05-21T10:00:07+00:00",
                ),
                (
                    "match",
                    "2026-05-21T10:00:08+00:00",
                    "2026-05-21T10:00:20+00:00",
                    "2026-05-21T10:00:23+00:00",
                ),
            ],
        )

    metrics = compute_metrics()

    assert metrics["avg_duration_s"] == 8.0
    assert metrics["per_review"][0]["duration_s"] == 8.0


def test_metrics_prefer_active_step_duration_over_review_span(sqlite_repo):
    _seed_review(sqlite_repo)
    sqlite_repo.save_progress(
        "review-1",
        {
            "review_id": "review-1",
            "status": "completed",
            "created_at": "2026-05-21T10:00:00+00:00",
            "updated_at": "2026-05-21T10:00:30+00:00",
            "steps": [
                {
                    "name": "Extraktion",
                    "status": "completed",
                    "started_at": "2026-05-21T10:00:02+00:00",
                    "completed_at": "2026-05-21T10:00:07+00:00",
                },
                {
                    "name": "Matching",
                    "status": "completed",
                    "started_at": "2026-05-21T10:00:20+00:00",
                    "completed_at": "2026-05-21T10:00:23+00:00",
                },
            ],
            "result": {"summary": {"duration_s": 20.0}},
            "error": None,
        },
    )

    metrics = compute_metrics()

    assert metrics["avg_duration_s"] == 8.0
    assert metrics["per_review"][0]["duration_s"] == 8.0


def test_metrics_include_review_creation_to_approval_duration(sqlite_repo):
    _seed_review(sqlite_repo)
    with sqlite_repo.connect() as conn:
        conn.execute(
            "UPDATE reviews SET created_at=? WHERE review_id='review-1'",
            ("2026-05-21T10:00:00+00:00",),
        )
    sqlite_repo.save_approval(
        "review-1",
        {
            "state": "approved",
            "approved_at": "2026-05-21T10:03:30+00:00",
            "approved_by": "Julian",
        },
    )

    metrics = compute_metrics()

    assert metrics["reviews_with_approval_duration"] == 1
    assert metrics["avg_approval_duration_s"] == 210.0
    assert metrics["per_review"][0]["approval_duration_s"] == 210.0
    assert metrics["per_review"][0]["approved_at"] == "2026-05-21T10:03:30+00:00"


def test_metrics_sum_all_recorded_llm_usage_sources(sqlite_repo):
    _seed_review(sqlite_repo)
    sqlite_repo.record_llm_usage(
        "review-1",
        source="extraction",
        usage={"input_tokens": 100, "output_tokens": 25, "total_tokens": 125},
    )
    sqlite_repo.record_llm_usage(
        "review-1",
        source="reply_body",
        usage={"input_tokens": 40, "output_tokens": 10, "total_tokens": 50},
    )

    metrics = compute_metrics()

    assert metrics["llm_calls"] == 1
    assert metrics["total_input_tokens"] == 140
    assert metrics["total_output_tokens"] == 35
    assert metrics["total_tokens"] == 175
    assert metrics["per_review"][0]["token_usage"] == {
        "input_tokens": 140,
        "output_tokens": 35,
        "total_tokens": 175,
    }


def test_metrics_count_persisted_fast_path_extraction(sqlite_repo):
    _seed_review(sqlite_repo)
    sqlite_repo.save_extraction_meta("review-1", path="fast_path")

    metrics = compute_metrics()

    assert metrics["fast_path_hits"] == 1
    assert metrics["llm_calls"] == 0
    assert metrics["per_review"][0]["extraction_path"] == "fast_path"


def test_metrics_infer_legacy_no_token_review_as_fast_path(sqlite_repo):
    _seed_review(sqlite_repo)

    metrics = compute_metrics()

    assert metrics["fast_path_hits"] == 1
    assert metrics["llm_calls"] == 0
    assert metrics["per_review"][0]["extraction_path"] == "fast_path"
