from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import ValidationError

from quoting.api.services.review_service import (
    ReviewDataService,
    enrich_exact_article_edits,
)
from quoting.api.use_cases.errors import UseCaseBadRequest, UseCaseUnprocessable
from quoting.core import Anfrage
from quoting.matching import match_positions
from quoting.pipeline import QuotingPipeline
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

log = logging.getLogger("quoting.frontend_router")


@dataclass
class UpdateAnfrageUseCase:
    repo: SQLiteReviewRepository
    pipeline: QuotingPipeline
    review_data: ReviewDataService

    def execute(self, review_id: str, payload: dict) -> dict:
        try:
            anfrage = Anfrage.model_validate(payload)
        except ValidationError as exc:
            raise UseCaseBadRequest(f"Invalid Anfrage payload: {exc}") from exc

        previous = self.review_data.try_load_anfrage(review_id)
        anfrage = enrich_exact_article_edits(anfrage, previous, self.pipeline)

        self.repo.save_anfrage_reviewed(review_id, anfrage.model_dump(mode="json"))
        if self.repo.has_matches_reviewed(review_id):
            matches = self.review_data.load_or_recompute_matches(
                review_id,
                anfrage,
                self.pipeline,
            )
            self.repo.save_matches_reviewed(review_id, [m.to_dict() for m in matches])
        else:
            try:
                matches = match_positions(
                    anfrage.positionen,
                    self.pipeline.stammdaten,
                    fuzzy_threshold=self.pipeline.settings.fuzzy_threshold,
                    semantic_threshold=self.pipeline.settings.semantic_threshold,
                )
            except Exception as exc:
                log.exception("put_anfrage: match recompute failed for %s", review_id)
                raise UseCaseUnprocessable(f"Matching fehlgeschlagen: {exc}") from exc
            self.repo.save_matches_initial(review_id, [m.to_dict() for m in matches])

        self.review_data.invalidate_approval(review_id)
        return anfrage.model_dump(mode="json")


@dataclass
class SaveOverridesUseCase:
    repo: SQLiteReviewRepository
    review_data: ReviewDataService

    def execute(self, review_id: str, payload: list[dict]) -> list[dict]:
        if not isinstance(payload, list):
            raise UseCaseBadRequest("Overrides payload must be a list")

        self.repo.save_overrides(review_id, payload)
        self.review_data.invalidate_approval(review_id)
        return payload
