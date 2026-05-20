from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from quoting.api.approval_store import ApprovalStore
from quoting.api.progress_store import ProgressStore
from quoting.api.use_cases.common import build_review_response
from quoting.api.use_cases.dtos import IncomingMailAttachment, IncomingMailReview
from quoting.api.use_cases.errors import UseCaseBadRequest, UseCaseError
from quoting.ingestion import Mail
from quoting.reviews.sqlite_repository import SQLiteReviewRepository

if TYPE_CHECKING:
    from quoting.api.pipeline_coordinator import PipelineCoordinator


@dataclass
class CreateReviewFromMailUseCase:
    repo: SQLiteReviewRepository
    progress_store: ProgressStore
    approval_store: ApprovalStore
    coordinator: PipelineCoordinator
    review_ui_base_url: str

    def execute(self, payload: IncomingMailReview) -> dict:
        review_id = uuid.uuid4().hex[:12]
        self.repo.create_review(
            review_id,
            subject=payload.subject,
            sender=payload.sender,
            body=payload.body,
            source="outlook",
            outlook_item_id=payload.outlook_item_id,
        )
        folder = self.repo.artifact_dir(review_id)
        folder.mkdir(parents=True, exist_ok=True)

        self.progress_store.init(review_id)
        self.approval_store.reset(review_id)

        try:
            self._prepare_mail_payload(payload, review_id, folder)
            self.progress_store.update_step(
                review_id,
                "Mail vorbereiten",
                "completed",
                "Mail und Anhänge gespeichert",
            )
        except UseCaseError as exc:
            self.progress_store.fail(review_id, str(exc))
            raise
        except Exception as exc:
            self.progress_store.fail(review_id, str(exc))
            raise UseCaseBadRequest(f"Could not prepare mail: {exc}") from exc

        self.coordinator.start_pipeline(review_id)
        return build_review_response(
            review_id,
            status="running",
            review_ui_base_url=self.review_ui_base_url,
        )

    def _decode_and_save_attachments(
        self,
        attachments: list[IncomingMailAttachment],
        review_id: str,
        folder: Path,
    ) -> list[Path]:
        saved: list[Path] = []
        for attachment in attachments:
            if not attachment.content_base64:
                continue
            safe_name = Path(attachment.name).name or f"attachment_{len(saved)}"
            target = folder / safe_name
            try:
                target.write_bytes(base64.b64decode(attachment.content_base64))
            except Exception as exc:
                raise UseCaseBadRequest(
                    f"Bad base64 in attachment '{attachment.name}': {exc}",
                ) from exc
            self.repo.register_document(
                review_id,
                kind="attachment",
                path=target,
                filename=safe_name,
                content_type=attachment.content_type,
            )
            saved.append(target)
        return saved

    def _prepare_mail_payload(
        self,
        payload: IncomingMailReview,
        review_id: str,
        folder: Path,
    ) -> Mail:
        meta = {
            "subject": payload.subject,
            "from": payload.sender,
            "body": payload.body,
            "attachments": [attachment.meta_dict() for attachment in payload.attachments],
        }
        self.repo.save_mail(review_id, meta)

        saved_paths = self._decode_and_save_attachments(
            payload.attachments,
            review_id,
            folder,
        )

        mail = Mail(
            subject=payload.subject,
            sender=payload.sender,
            body=payload.body,
            attachments=saved_paths,
        )
        if not mail.has_content:
            raise UseCaseBadRequest(
                "Mail has neither body text nor attachments — nothing to extract.",
            )
        return mail
