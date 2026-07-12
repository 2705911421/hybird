from __future__ import annotations

from typing import Any


class RuntimeErrorBase(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        current_revision: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.current_revision = current_revision
        self.details = details or {}


class NotFoundError(RuntimeErrorBase):
    pass


class DatabaseUnavailableError(RuntimeErrorBase):
    pass


class FeatureDisabledError(RuntimeErrorBase):
    pass
