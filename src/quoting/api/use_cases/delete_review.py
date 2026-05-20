from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass

from quoting.api.use_cases.errors import UseCaseFailure
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

log = logging.getLogger("quoting.frontend_router")


@dataclass
class DeleteReviewUseCase:
    repo: SQLiteReviewRepository

    def execute(self, review_id: str) -> None:
        folder = self.repo.artifact_dir(review_id)
        try:
            if folder.exists():
                shutil.rmtree(folder)
            self.repo.delete_review(review_id)
        except OSError as exc:
            log.exception("delete_review: could not delete %s", review_id)
            raise UseCaseFailure(f"Review konnte nicht gelöscht werden: {exc}") from exc
