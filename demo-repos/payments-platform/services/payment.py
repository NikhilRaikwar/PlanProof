from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from services.provider import PaymentProvider, ProviderRefund


@dataclass(frozen=True)
class Payment:
    id: str
    provider_payment_id: str
    captured_amount: Decimal


class PaymentService:
    """Current behavior: exactly one full refund, with no amount parameter."""

    def __init__(self, provider: PaymentProvider) -> None:
        self._provider = provider

    def refund(self, payment: Payment) -> ProviderRefund:
        return self._provider.refund(
            provider_payment_id=payment.provider_payment_id,
            amount=payment.captured_amount,
        )
