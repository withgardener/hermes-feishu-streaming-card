"""Delivery results shared by transports and orchestration, without I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .message_navigation import MessageNavigation


DeliveryFailureOutcome = Literal["not_sent", "unknown"]


class FeishuAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        api_code: int | str | None = None,
        retryable: bool = False,
        outcome: DeliveryFailureOutcome = "not_sent",
        retry_after_seconds: float | None = None,
        retry_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.api_code = api_code
        self.retryable = retryable
        self.outcome = outcome
        self.retry_after_seconds = retry_after_seconds
        self.retry_count = retry_count


@dataclass(frozen=True)
class CardDeliveryResult:
    message_id: str | None
    outcome: str
    retry_count: int = 0
    error_kind: str = ""
    navigation: MessageNavigation | None = field(default=None, repr=False)

    @property
    def delivered(self) -> bool:
        return self.outcome == "delivered" and bool(self.message_id)
