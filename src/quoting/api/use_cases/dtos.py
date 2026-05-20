from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IncomingMailAttachment:
    name: str
    content_type: str | None = None
    size: int | None = None
    id: str | None = None
    content_base64: str | None = None

    def meta_dict(self) -> dict:
        result: dict[str, Any] = {"name": self.name}
        if self.content_type is not None:
            result["contentType"] = self.content_type
        if self.size is not None:
            result["size"] = self.size
        if self.id is not None:
            result["id"] = self.id
        return result


@dataclass(frozen=True)
class IncomingMailReview:
    subject: str
    sender: str
    body: str
    attachments: list[IncomingMailAttachment]
    outlook_item_id: str | None = None
