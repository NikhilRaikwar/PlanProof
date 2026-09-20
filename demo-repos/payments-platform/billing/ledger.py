from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RefundEvent:
    payment_id: str
    captured_amount: Decimal
    refund_amount: Decimal


def refund_ledger_debit(event: RefundEvent) -> Decimal:
    """Known defect: invoices are debited by the full capture, not the partial refund amount."""

    return -event.captured_amount
