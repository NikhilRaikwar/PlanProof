export interface Obligation {
  id: string
  title: string
  category: 'BEHAVIOR' | 'DATA_MODEL' | 'API_CONTRACT' | 'DEPENDENCY' | 'BUSINESS_RULE' | 'COMPATIBILITY'
  status: 'verified' | 'disproved' | 'inconclusive' | 'human'
  criticality: 'CRITICAL' | 'HIGH' | 'MEDIUM'
  file: string
  lineRange: string
  rationale: string
  codeSnippet?: string
  counterEvidence?: string
  remediation?: string
  humanDecisionPrompt?: {
    question: string
    options: string[]
  }
}

export interface EvidenceItem {
  id: string
  indexStr: string
  title: string
  sourcePath: string
  summaryFact: string
  status: 'disproved' | 'verified' | 'human' | 'inconclusive'
  sourceType: 'Code' | 'API Contract' | 'Business Rule'
  language: string
  lines: string
  lastModified: string
  whyItMatters: string
  codeExcerpt: string
  relatedClaims: { id: string; title: string; status: 'disproved' | 'verified' | 'human' | 'inconclusive' }[]
}

export interface ToolTraceItem {
  id: string
  name: string
  desc: string
  status: 'COMPLETED' | 'RUNNING' | 'PENDING'
  duration: string
}

export interface VerificationRunItem {
  id: string
  runNumber: string
  title: string
  repo: string
  branch: string
  commit: string
  status: 'BLOCKED' | 'VERIFIED'
  coverage: number
  claimsTotal: number
  disprovedCount: number
  verifiedCount: number
  humanCount: number
  inconclusiveCount: number
  duration: string
  timestamp: string
}

export const defaultObligations: Obligation[] = [
  {
    id: 'ob-1',
    title: 'PaymentService supports partial refund amounts',
    category: 'BEHAVIOR',
    status: 'disproved',
    criticality: 'CRITICAL',
    file: 'services/payment.py',
    lineRange: 'lines 84–108',
    rationale: 'The candidate plan assumes the current refund method takes an optional amount, but the existing codebase always refunds the full captured_amount.',
    codeSnippet: `def refund(self, payment_id: str):
    payment = self.get_payment(payment_id)
    # Existing implementation hardcodes full captured amount
    return self.provider.refund(
        payment.provider_id,
        amount=payment.captured_amount
    )`,
    counterEvidence: 'PaymentService.refund() ignores custom amount parameters and relies strictly on payment.captured_amount. Passing partial amounts will cause silent full refunds.',
    remediation: 'Update PaymentService.refund(self, payment_id: str, amount: Optional[Decimal] = None) and validate amount <= payment.captured_amount - payment.refunded_total.'
  },
  {
    id: 'ob-2',
    title: 'Refunds can be stored as multiple records per payment',
    category: 'DATA_MODEL',
    status: 'disproved',
    criticality: 'CRITICAL',
    file: 'db/models/refund.ts',
    lineRange: 'line 22',
    rationale: 'The plan assumes no database schema changes are required. However, the refund entity enforces a UNIQUE constraint on payment_id.',
    codeSnippet: `@Entity('refunds')
export class RefundEntity {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  // CONFLICT: Unique constraint permits only ONE refund record per payment
  @Column({ unique: true })
  payment_id: string;

  @Column('decimal', { precision: 10, scale: 2 })
  amount: number;
}`,
    counterEvidence: 'Table `refunds` has a UNIQUE INDEX on `payment_id`. Attempting a second partial refund will throw a Database Constraint Violation (SQL Error 23505).',
    remediation: 'Create a migration removing UNIQUE(payment_id) and introduce an aggregate column `refunded_total` on `payments` table.'
  },
  {
    id: 'ob-3',
    title: 'Maximum refund amount authorization policy',
    category: 'BUSINESS_RULE',
    status: 'human',
    criticality: 'CRITICAL',
    file: 'services/auth.py',
    lineRange: 'lines 201–228',
    rationale: 'The change request does not specify if partial refunds should be permitted on flagged/unverified accounts without manual manager escalation.',
    humanDecisionPrompt: {
      question: 'What is the refund authorization threshold for non-verified merchant accounts?',
      options: [
        'Cap automated partial refunds to <= $500; require Manager MFA above $500',
        'Allow partial refunds up to 100% of original transaction without manual gate',
        'Block all automated partial refunds on unverified accounts'
      ]
    },
    remediation: 'Apply chosen product policy into SecurityGate middleware before calling StripeProvider.'
  },
  {
    id: 'ob-4',
    title: 'Existing idempotency prevents duplicate refunds',
    category: 'COMPATIBILITY',
    status: 'verified',
    criticality: 'HIGH',
    file: 'api/idempotency.ts',
    lineRange: 'lines 31–58',
    rationale: 'Idempotency middleware tracks SHA-256 payload hashes and Redis lock keys correctly for all POST /v1/payments/:id/refunds calls.',
    codeSnippet: `export async function checkIdempotency(key: string, payload: any) {
  const lock = await redis.set(\`idemp:\${key}\`, 'LOCKED', 'NX', 'EX', 120);
  if (!lock) throw new ConflictError('Concurrent request in flight');
  return true;
}`
  },
  {
    id: 'ob-5',
    title: 'Billing totals are calculated from refund events',
    category: 'DEPENDENCY',
    status: 'verified',
    criticality: 'HIGH',
    file: 'billing/ledger.py',
    lineRange: 'lines 140–176',
    rationale: 'Ledger consumers handle decimal amounts dynamically using Kafka `payment.refunded` event schemas without assumption of full amount.',
    codeSnippet: `def handle_refund_event(event: RefundEvent):
    # Ledger aggregates whatever decimal amount is received
    ledger.record_debit(event.merchant_id, event.amount)`
  },
  {
    id: 'ob-6',
    title: 'Mobile clients accept a partial refund response',
    category: 'API_CONTRACT',
    status: 'inconclusive',
    criticality: 'MEDIUM',
    file: 'openapi/payments.yaml',
    lineRange: 'lines 210–245',
    rationale: 'OpenAPI response schema specifies `status: "refunded" | "pending"`. Mobile SDK v3.2 may not render `status: "partially_refunded"` badge.',
    counterEvidence: 'OpenAPI spec does not explicitly document client backward-compatibility for partial enum values.',
    remediation: 'Maintain `status: "refunded"` with a new field `refund_type: "partial"` for older clients.'
  }
]

export const defaultEvidenceList: EvidenceItem[] = [
  {
    id: 'ev-1',
    indexStr: '01',
    title: 'PaymentService refund implementation',
    sourcePath: 'services/payment.py',
    summaryFact: 'PaymentService.refund() ignores custom amount parameters and always refunds the full captured amount.',
    status: 'disproved',
    sourceType: 'Code',
    language: 'Python',
    lines: '84–108',
    lastModified: '3 days ago',
    whyItMatters: 'This directly contradicts the plan assumption that the refund method takes an optional amount and supports partial refunds. The implementation always uses payment.captured_amount, so passing a custom amount has no effect.',
    codeExcerpt: `services/payment.py
84  def refund(self, payment_id: str):
85      payment = self.get_payment(payment_id)
86      # Existing implementation hardcodes full captured amount
87      return self.provider.refund(
88          payment.provider_id,
89          amount=payment.captured_amount
90      )`,
    relatedClaims: [
      { id: 'C01', title: 'PaymentService supports partial refund amounts', status: 'disproved' },
      { id: 'C05', title: 'Billing totals are calculated from refund events', status: 'verified' }
    ]
  },
  {
    id: 'ev-2',
    indexStr: '02',
    title: 'Refund model unique index',
    sourcePath: 'db/models/refund.ts',
    summaryFact: 'Unique index on (payment_id) prevents multiple refund records for the same payment.',
    status: 'verified',
    sourceType: 'Code',
    language: 'TypeScript',
    lines: '12–28',
    lastModified: '1 week ago',
    whyItMatters: 'Attempting to store multiple partial refund records per payment will fail at the database level due to the unique constraint on payment_id unless an explicit migration is performed.',
    codeExcerpt: `db/models/refund.ts
12  @Entity('refunds')
13  export class RefundEntity {
14    @PrimaryGeneratedColumn('uuid')
15    id: string;
16  
17    @Column({ unique: true })
18    payment_id: string;
19  
20    @Column('decimal', { precision: 10, scale: 2 })
21    amount: number;
22  }`,
    relatedClaims: [
      { id: 'C02', title: 'Refunds can be stored as multiple records per payment', status: 'disproved' }
    ]
  },
  {
    id: 'ev-3',
    indexStr: '03',
    title: 'Billing ledger dependency',
    sourcePath: 'billing/ledger.py',
    summaryFact: 'Refund events create negative ledger entries used to calculate billing totals.',
    status: 'verified',
    sourceType: 'Code',
    language: 'Python',
    lines: '45–73',
    lastModified: '2 weeks ago',
    whyItMatters: 'Verifies that billing calculations will correctly reflect partial refund amounts passed via event payloads without unexpected whole-balance debiting.',
    codeExcerpt: `billing/ledger.py
45  def handle_refund_event(event: RefundEvent):
46      # Ledger aggregates whatever decimal amount is received
47      ledger.record_debit(
48          merchant_id=event.merchant_id, 
49          amount=event.amount
50      )`,
    relatedClaims: [
      { id: 'C05', title: 'Billing totals are calculated from refund events', status: 'verified' }
    ]
  },
  {
    id: 'ev-4',
    indexStr: '04',
    title: 'Idempotency middleware',
    sourcePath: 'api/idempotency.ts',
    summaryFact: 'Idempotency key middleware prevents duplicate refund requests from creating multiple refunds.',
    status: 'human',
    sourceType: 'Code',
    language: 'TypeScript',
    lines: '10–42',
    lastModified: '5 days ago',
    whyItMatters: 'Idempotency locking keys use a combination of request ID and body hash. If partial refund payloads share the same idempotency key, subsequent valid partial refunds will be blocked.',
    codeExcerpt: `api/idempotency.ts
10  export async function checkIdempotency(key: string, payload: any) {
11    const lock = await redis.set(\`idemp:\${key}\`, 'LOCKED', 'NX', 'EX', 120);
12    if (!lock) throw new ConflictError('Concurrent request in flight');
13    return true;
14  }`,
    relatedClaims: [
      { id: 'C04', title: 'Existing idempotency prevents duplicate refunds', status: 'verified' }
    ]
  },
  {
    id: 'ev-5',
    indexStr: '05',
    title: 'OpenAPI refund response contract',
    sourcePath: 'openapi/payments.yaml',
    summaryFact: 'POST /payments/{id}/refund returns a refund object with refunded_amount equal to the full captured amount.',
    status: 'inconclusive',
    sourceType: 'API Contract',
    language: 'YAML',
    lines: '120–158',
    lastModified: '1 month ago',
    whyItMatters: 'Downstream client SDKs depend on the status enum schema. Returning a partial status code could break legacy mobile and integration SDKs expecting binary refunded states.',
    codeExcerpt: `openapi/payments.yaml
120  /payments/{id}/refund:
121    post:
122      summary: Issue refund
123      responses:
124        '200':
125          schema:
126            $ref: '#/definitions/RefundResponse'`,
    relatedClaims: [
      { id: 'C06', title: 'Mobile clients accept a partial refund response', status: 'inconclusive' }
    ]
  },
  {
    id: 'ev-6',
    indexStr: '06',
    title: 'Refund authorization rules',
    sourcePath: 'services/auth.py',
    summaryFact: 'Only captures with status=SUCCEEDED can be refunded.',
    status: 'verified',
    sourceType: 'Code',
    language: 'Python',
    lines: '201–228',
    lastModified: '2 weeks ago',
    whyItMatters: 'Guarantees that pending or authorized-only transactions cannot be partially refunded before settlement confirmation.',
    codeExcerpt: `services/auth.py
201  def can_refund(payment: Payment) -> bool:
202      if payment.status != PaymentStatus.SUCCEEDED:
203          return False
204      return payment.captured_amount > payment.refunded_total`,
    relatedClaims: [
      { id: 'C03', title: 'Maximum refund amount authorization policy', status: 'human' }
    ]
  }
]

export const defaultToolTraces: ToolTraceItem[] = [
  { id: 't-1', name: 'claim_extraction', desc: 'Extract and normalize verification claims from the plan and repository context.', status: 'COMPLETED', duration: '12.3s' },
  { id: 't-2', name: 'symbol_search', desc: 'Find relevant symbols, classes, and functions in the codebase.', status: 'COMPLETED', duration: '18.7s' },
  { id: 't-3', name: 'schema_probe', desc: 'Inspect data models and schemas for refund-related entities.', status: 'COMPLETED', duration: '14.1s' },
  { id: 't-4', name: 'dependency_graph', desc: 'Build dependency graph for impacted components.', status: 'COMPLETED', duration: '11.6s' },
  { id: 't-5', name: 'openapi_scan', desc: 'Analyze API contracts and request/response schemas.', status: 'COMPLETED', duration: '16.9s' },
  { id: 't-6', name: 'contradiction_check', desc: 'Check claims against code evidence for contradictions.', status: 'COMPLETED', duration: '20.4s' }
]

export const defaultRunsList: VerificationRunItem[] = [
  {
    id: 'run-101',
    runNumber: '#101',
    title: 'Partial Refunds / PlanGate',
    repo: 'nikhilraikwar / planproof',
    branch: 'main',
    commit: '8f3c1a2',
    status: 'BLOCKED',
    coverage: 83,
    claimsTotal: 6,
    disprovedCount: 2,
    verifiedCount: 2,
    humanCount: 1,
    inconclusiveCount: 1,
    duration: '38s',
    timestamp: 'Just now'
  },
  {
    id: 'run-100',
    runNumber: '#100',
    title: 'Idempotency Redis Lock Migration',
    repo: 'nikhilraikwar / payments-service',
    branch: 'main',
    commit: 'a1d9e4f',
    status: 'VERIFIED',
    coverage: 100,
    claimsTotal: 4,
    disprovedCount: 0,
    verifiedCount: 4,
    humanCount: 0,
    inconclusiveCount: 0,
    duration: '24s',
    timestamp: '2 hours ago'
  },
  {
    id: 'run-099',
    runNumber: '#099',
    title: 'Stripe Webhook Signature Verification',
    repo: 'nikhilraikwar / billing-platform',
    branch: 'main',
    commit: 'c7e2b91',
    status: 'VERIFIED',
    coverage: 95,
    claimsTotal: 8,
    disprovedCount: 0,
    verifiedCount: 7,
    humanCount: 1,
    inconclusiveCount: 0,
    duration: '42s',
    timestamp: '1 day ago'
  }
]
