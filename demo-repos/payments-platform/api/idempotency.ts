export type IdempotencyRecord = {
  paymentId: string
  requestId: string
}

/**
 * Known defect: partial refund amount is not part of the lock identity.
 * A second legitimate partial refund for the same payment will collide.
 */
export function refundIdempotencyKey(paymentId: string): string {
  return `refund:${paymentId}`
}
