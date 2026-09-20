from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ProviderRefund:
    provider_refund_id: str
    amount: Decimal


class PaymentProvider:
    """The external provider already accepts a partial-refund amount."""

    def refund(self, provider_payment_id: str, amount: Decimal) -> ProviderRefund:
        if amount <= Decimal("0"):
            raise ValueError("refund amount must be positive")
        return ProviderRefund(provider_refund_id=f"re_{provider_payment_id}", amount=amount)
