from __future__ import annotations

from typing import Any


class UseCaseError(Exception):
    """Base error for application use-cases.

    Use-cases raise these framework-neutral errors. HTTP adapters translate
    them to transport-specific responses.
    """

    def __init__(self, detail: str | dict[str, Any]) -> None:
        self.detail = detail
        super().__init__(str(detail))


class UseCaseBadRequest(UseCaseError):
    pass


class UseCaseConflict(UseCaseError):
    pass


class UseCaseUnprocessable(UseCaseError):
    pass


class UseCaseFailure(UseCaseError):
    pass
