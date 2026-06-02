"""Idempotent pipeline-step handlers.

Stage 2 of the job-queue refactor. Each handler takes a ``review_id``,
loads its inputs from SQLite (preferring user-reviewed payloads where
they exist), checks whether its output is already there, and either
short-circuits or delegates to the existing
:class:`~quoting.pipeline.QuotingPipeline` step.

Why short-circuiting matters
----------------------------
The job worker may retry a handler after a transient failure further
downstream, or after a process crash. Without idempotency, a retry of
``extract`` would burn another LLM call even though the output is
already on disk. The skip-if-output-exists check makes retries cheap
and safe.

What counts as "output already there"
-------------------------------------
- ``extract`` → :data:`Payloads.EXTRACTED` exists.
- ``match``   → :data:`Payloads.MATCHES` exists.
- ``price``   → :data:`Payloads.QUOTATION` exists.
- ``render``  → a current ``draft_pdf`` document exists *and* its file
  is still on disk (filesystems and DB can drift if someone deletes
  artifacts under us).

User-edited payloads (``ANFRAGE_REVIEWED``, ``MATCHES_REVIEWED``,
``QUOTATION_REVIEWED``) are read as inputs for downstream steps but
never written by the handlers — those belong to the review UI's
mutation paths.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quoting.api.progress_store import ProgressStore
from quoting.api.services.review_service import (
    ReviewDataService,
    match_from_dict,
    match_positions_with_settings,
)
from quoting.api.settings_store import AppSettings, load_user_settings
from quoting.core import Anfrage
from quoting.matching import MatchResult
from quoting.pipeline import QuotingPipeline, StepContext, StepProgress
from quoting.pricing import Quotation
from quoting.reviews import draft_pdf_filename
from quoting.reviews.quotation_store import quotation_from_dict
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

SettingsLoader = Callable[[], AppSettings]


class StepInputMissing(RuntimeError):
    """Raised when a handler can't find a required upstream payload.

    Distinct from a step-internal failure (LLM down, bad CSV, etc.) so
    callers and tests can tell the difference between "the pipeline was
    invoked out of order" and "the step itself blew up".
    """


@dataclass
class StepHandlers:
    repo: SQLiteReviewRepository
    pipeline: QuotingPipeline
    progress_store: ProgressStore
    settings_loader: SettingsLoader = load_user_settings
    _data_service: ReviewDataService | None = field(default=None, init=False, repr=False)

    @property
    def data_service(self) -> ReviewDataService:
        if self._data_service is None:
            self._data_service = ReviewDataService(
                self.repo,
                settings_loader=self.settings_loader,
            )
        return self._data_service

    # ---------------------------------------------------------------- helpers
    _PAYLOAD_EVENT_MAP = {
        "extracted": "extracted",
        "matches": "matched",
        "quotation": "priced",
    }

    def _ctx(self, review_id: str) -> StepContext:
        """StepContext wired to persist payloads + report progress for ``review_id``."""
        folder = self.repo.artifact_dir(review_id)

        def snapshot_sink(name: str, data: Any) -> None:
            self.repo.save_payload(review_id, name, data)
            event_name = self._PAYLOAD_EVENT_MAP.get(name)
            if event_name is not None:
                self.progress_store.bus.publish(
                    review_id,
                    {"event": event_name, "data": data},
                )

        def on_progress(progress: StepProgress) -> None:
            self.progress_store.update_step(
                review_id=review_id,
                step_name=progress.step_name,
                status=progress.status,
                detail=progress.detail,
                metadata=progress.metadata,
            )

        return StepContext(
            work_dir=folder,
            progress=on_progress,
            snapshot_sink=snapshot_sink,
        )

    def _load_anfrage(self, review_id: str) -> Anfrage:
        anfrage = self.data_service.try_load_anfrage(review_id)
        if anfrage is None:
            raise StepInputMissing(
                f"No anfrage for review {review_id!r} — extract must run first"
            )
        return anfrage

    def _load_matches(self, review_id: str) -> list[MatchResult]:
        raw = self.repo.load_matches(review_id)
        if not raw:
            raise StepInputMissing(
                f"No matches for review {review_id!r} — match must run first"
            )
        return [match_from_dict(item) for item in raw if isinstance(item, dict)]

    # ----------------------------------------------------------------- steps
    def extract(self, review_id: str) -> None:
        if self.repo.load_extracted(review_id) is not None:
            return  # already done

        mail_meta = self.repo.load_mail(review_id)
        if mail_meta is None:
            raise StepInputMissing(
                f"No mail payload for review {review_id!r} — cannot extract"
            )
        mail = self.data_service.mail_from_meta(mail_meta, review_id)
        if not mail.has_content:
            raise StepInputMissing(
                f"Mail for review {review_id!r} has no body and no attachments"
            )

        ctx = self._ctx(review_id)
        self.pipeline.extract(mail, ctx)
        extraction_path = ctx.extra.get("extraction_path")
        if extraction_path in {"fast_path", "llm"}:
            self.repo.save_extraction_meta(review_id, path=str(extraction_path))
        usage = ctx.extra.get("token_usage")
        if usage is not None:
            self.repo.record_llm_usage(
                review_id,
                source="extraction",
                usage=usage,
            )

    def match(self, review_id: str) -> None:
        if self.repo.load_matches_initial(review_id) is not None:
            return  # already done

        anfrage = self._load_anfrage(review_id)
        ctx = self._ctx(review_id)
        ctx.report(
            "Matching",
            "started",
            f"{len(anfrage.positionen)} Positionen vs. {len(self.pipeline.stammdaten)} Stammdaten",
        )
        matches = match_positions_with_settings(
            anfrage,
            self.pipeline,
            self.settings_loader,
        )
        ctx.persist("matches", [m.to_dict() for m in matches])
        exact = sum(1 for m in matches if m.status == "exact")
        no_match = sum(1 for m in matches if m.status == "no_match")
        ctx.report("Matching", "completed", f"{exact} exakt, {no_match} kein Treffer")

    def price(self, review_id: str) -> None:
        if self.repo.load_quotation_initial(review_id) is not None:
            return  # already done

        anfrage = self._load_anfrage(review_id)
        matches = self._load_matches(review_id)
        self.pipeline.price(anfrage, matches, self._ctx(review_id))

    def render(self, review_id: str) -> None:
        existing = self.repo.current_document(review_id, kind="draft_pdf")
        if existing is not None:
            existing_path = Path(str(existing.get("storage_path") or ""))
            if existing_path.exists():
                return  # already done

        anfrage = self._load_anfrage(review_id)
        quotation_dict = self.repo.load_quotation(review_id)
        if quotation_dict is None:
            raise StepInputMissing(
                f"No quotation for review {review_id!r} — price must run first"
            )
        quotation: Quotation = quotation_from_dict(quotation_dict)

        folder = self.repo.artifact_dir(review_id)
        pdf_path = folder / draft_pdf_filename(review_id)
        company_profile = self.settings_loader().company
        self.pipeline.render(anfrage, quotation, pdf_path, self._ctx(review_id), company_profile=company_profile)

        self.repo.register_document(
            review_id,
            kind="draft_pdf",
            path=pdf_path,
            filename=pdf_path.name,
            content_type="application/pdf",
        )
