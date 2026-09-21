import { expect, Page, test } from '@playwright/test'

const projectA = {
  id: 'proj-averix',
  name: 'NikhilRaikwar/Averix-AI',
  owner_id: 'test-user',
  repository_source_type: 'github_app',
  data_scope: 'USER',
  requested_ref: 'main',
  github_repository_id: 1001,
  github_installation_id: 12345,
  created_at: '2026-09-21T00:00:00Z'
}

const projectB = {
  id: 'proj-service',
  name: 'NikhilRaikwar/Payment-Service',
  owner_id: 'test-user',
  repository_source_type: 'github_app',
  data_scope: 'USER',
  requested_ref: 'main',
  github_repository_id: 1002,
  github_installation_id: 12345,
  created_at: '2026-09-21T00:00:00Z'
}

const snapshotA = {
  id: 'snap-4255cdc',
  project_id: projectA.id,
  repository_identity: 'NikhilRaikwar/Averix-AI',
  source_type: 'github_app',
  requested_ref: 'main',
  resolved_commit_sha: '4255cdc1234567890abcdef1234567890abcdef',
  status: 'READY',
  files_indexed: 42,
  symbols_indexed: 180,
  ignored_files: 2,
  supported_languages: ['python'],
  created_at: '2026-09-21T00:00:00Z',
  updated_at: '2026-09-21T00:00:00Z'
}

const snapshotB = {
  id: 'snap-8899aabb',
  project_id: projectB.id,
  repository_identity: 'NikhilRaikwar/Payment-Service',
  source_type: 'github_app',
  requested_ref: 'main',
  resolved_commit_sha: '8899aabbccddeeff1234567890abcdef12345678',
  status: 'READY',
  files_indexed: 15,
  symbols_indexed: 64,
  ignored_files: 0,
  supported_languages: ['typescript'],
  created_at: '2026-09-21T00:00:00Z',
  updated_at: '2026-09-21T00:00:00Z'
}

const runForA = {
  id: 'run-averix-01',
  project_id: projectA.id,
  snapshot_id: snapshotA.id,
  plan_version_id: 'plan-1',
  status: 'COMPLETE',
  created_at: '2026-09-21T01:00:00Z',
  updated_at: '2026-09-21T01:05:00Z',
  tool_call_count: 5,
  model_call_count: 2,
  commit_sha: snapshotA.resolved_commit_sha,
  ref: 'main',
  plan_title: 'Add webhook signature validation',
  evidence_count: 4,
  tool_execution_count: 5,
  has_open_human_question: false
}

const runForB = {
  id: 'run-payment-02',
  project_id: projectB.id,
  snapshot_id: snapshotB.id,
  plan_version_id: 'plan-2',
  status: 'COMPLETE',
  created_at: '2026-09-21T02:00:00Z',
  updated_at: '2026-09-21T02:05:00Z',
  tool_call_count: 3,
  model_call_count: 1,
  commit_sha: snapshotB.resolved_commit_sha,
  ref: 'main',
  plan_title: 'Idempotency key enforcement',
  evidence_count: 2,
  tool_execution_count: 3,
  has_open_human_question: false
}

async function setupMockWorkspace(page: Page) {
  await page.route('**/health/ready', route => route.fulfill({ status: 200 }))
  await page.route('**/v1/auth/session', route => route.fulfill({
    json: { connected: true, account_login: 'test-user', installation_id: 12345 }
  }))
  await page.route(url => url.pathname === '/v1/workspace/projects', route => route.fulfill({
    json: [projectA, projectB]
  }))
  await page.route(url => url.pathname === '/v1/projects', route => route.fulfill({
    json: [projectA, projectB]
  }))
  await page.route('**/v1/github/repositories', route => route.fulfill({ json: [] }))
  await page.route(`**/v1/projects/${projectA.id}/snapshots`, route => route.fulfill({ json: [snapshotA] }))
  await page.route(`**/v1/projects/${projectB.id}/snapshots`, route => route.fulfill({ json: [snapshotB] }))

  await page.route(url => url.pathname === '/v1/verification-runs', route => {
    const requestUrl = new URL(route.request().url())
    const projId = requestUrl.searchParams.get('project_id')
    if (projId === projectA.id) {
      return route.fulfill({ json: [runForA] })
    }
    if (projId === projectB.id) {
      return route.fulfill({ json: [runForB] })
    }
    return route.fulfill({ json: [runForA, runForB] })
  })

  await page.route(`**/v1/verification-runs/${runForA.id}`, route => route.fulfill({
    json: {
      run: runForA,
      repository: { id: projectA.id, name: 'Averix-AI', full_name: projectA.name, repository_source_type: 'github_app' },
      snapshot: { id: snapshotA.id, requested_ref: 'main', resolved_commit_sha: snapshotA.resolved_commit_sha, status: 'READY' },
      plan: { id: 'plan-1', version: 1, change_request: 'Add webhook signature validation' },
      obligation_counts: { VERIFIED: 4 },
      human_questions: [],
      tool_runs: [],
      evidence_count: 4,
      tool_execution_count: 5,
      trace_attribution_status: 'EXACT'
    }
  }))

  await page.route(`**/v1/verification-runs/${runForB.id}`, route => route.fulfill({
    json: {
      run: runForB,
      repository: { id: projectB.id, name: 'Payment-Service', full_name: projectB.name, repository_source_type: 'github_app' },
      snapshot: { id: snapshotB.id, requested_ref: 'main', resolved_commit_sha: snapshotB.resolved_commit_sha, status: 'READY' },
      plan: { id: 'plan-2', version: 1, change_request: 'Idempotency key enforcement' },
      obligation_counts: { VERIFIED: 2 },
      human_questions: [
        {
          id: 'q-resolved-1',
          obligation_id: 'ob-1',
          question: 'Is partial refund supported for international cards?',
          why_needed: 'Card processor contract requires human authority.',
          authority_required: 'Lead Engineer',
          status: 'ANSWERED',
          answer: 'Approved with fallback to manual settlement.',
          answered_at: '2026-09-21T02:04:00Z'
        }
      ],
      tool_runs: [],
      evidence_count: 2,
      tool_execution_count: 3,
      trace_attribution_status: 'EXACT'
    }
  }))

  await page.route(`**/v1/verification-runs/${runForB.id}/proof-obligations`, route => route.fulfill({
    json: [
      {
        id: 'ob-1',
        statement: 'Refund service validates idempotency token',
        category: 'SAFETY',
        criticality: 'HIGH',
        status: 'VERIFIED',
        evidence_ids: ['ev-1'],
        counter_evidence_ids: []
      }
    ]
  }))

  await page.route(`**/v1/verification-runs/${runForB.id}/evidence`, route => route.fulfill({
    json: [
      {
        id: 'ev-1',
        snapshot_id: snapshotB.id,
        source_tool_run_id: 'tool-1',
        evidence_type: 'source_range',
        path: 'src/idempotency.ts',
        start_line: 12,
        end_line: 18,
        content_hash: '1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',
        safe_fact_summary: 'Unique constraint check verified on token parameter.',
        snippet: 'export function assertIdempotency(token: string) {\n  if (!token) throw new Error("Missing token");\n}',
        obligation_id: 'ob-1',
        relationship: 'SUPPORTS',
        created_at: '2026-09-21T02:02:00Z'
      }
    ]
  }))

  await page.route(`**/v1/verification-runs/${runForB.id}/tool-runs`, route => route.fulfill({
    json: [
      {
        id: 'tool-1',
        run_id: runForB.id,
        tool_name: 'search_code_lexical',
        status: 'SUCCEEDED',
        input_hash: 'abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdef',
        input_summary: { query: 'assertIdempotency', path_pattern: '*.ts' },
        result_count: 1,
        duration_ms: 18,
        started_at: '2026-09-21T02:01:30Z'
      }
    ]
  }))
}

test.describe('Workspace Context & Isolation', () => {
  test('unselected state shown when multiple repositories exist, and selecting repository updates topbar sticky context', async ({ page }) => {
    await setupMockWorkspace(page)
    await page.goto('/workspace')

    // Since 2 repositories exist and none is persisted, topbar shows "Select repository"
    await expect(page.getByText('Select repository').first()).toBeVisible()

    // Dashboard lists both connected repositories
    await expect(page.getByText('NikhilRaikwar/Averix-AI').first()).toBeVisible()
    await expect(page.getByText('NikhilRaikwar/Payment-Service').first()).toBeVisible()

    // Click "Set active" on Averix-AI
    await page.getByRole('button', { name: 'Set active' }).first().click()

    // Topbar chip immediately updates to Averix-AI with commit sha
    await expect(page.getByText('Averix-AI').first()).toBeVisible()
    await expect(page.getByText('4255cdc').first()).toBeVisible()

    // Navigate to /workspace/runs; context remains sticky
    await page.goto('/workspace/runs')
    await expect(page.getByText('Averix-AI').first()).toBeVisible()
    await expect(page.getByText('Add webhook signature validation')).toBeVisible()
    // Should NOT show Payment-Service run because runs are scoped to active repo
    await expect(page.getByText('Idempotency key enforcement')).not.toBeVisible()
  })

  test('run report page isolates run-authoritative context without corrupting global selected repo', async ({ page }) => {
    await setupMockWorkspace(page)
    
    // Pre-seed localStorage with Averix-AI as active workspace context
    await page.addInitScript(() => {
      localStorage.setItem('planproof:workspace-context:12345', JSON.stringify({
        repositoryId: 'proj-averix',
        repositoryFullName: 'NikhilRaikwar/Averix-AI',
        ref: 'main',
        snapshotId: 'snap-4255cdc',
        commitSha: '4255cdc1234567890abcdef1234567890abcdef',
        snapshotStatus: 'READY',
        dataScope: 'USER'
      }))
    })

    // Directly open a run belonging to Payment-Service (runForB)
    await page.goto(`/workspace/runs/${runForB.id}`)

    // Report derives context directly from run projection
    await expect(page.getByText('Gate: COMPLETE')).toBeVisible()
    await expect(page.getByText('Payment-Service').first()).toBeVisible()
    await expect(page.getByText('8899aab').first()).toBeVisible()
    await expect(page.getByText('Run-authoritative context:')).toBeVisible()

    // Topbar shows 'Run context' status indicator while viewing this run
    await expect(page.getByText('Run context')).toBeVisible()

    // Verify resolved human decision history rendered instead of active input form
    await expect(page.getByText('Resolved by authorized human decision')).toBeVisible()
    await expect(page.getByText('Approved with fallback to manual settlement.')).toBeVisible()
    await expect(page.getByText('Answer decision')).not.toBeVisible()

    // Verify code snippet is rendered from server-issued immutable evidence
    await expect(page.getByText('assertIdempotency')).toBeVisible()

    // Navigate back to /workspace/runs: persistent selected repo (Averix-AI) remains intact!
    await page.goto('/workspace/runs')
    await expect(page.getByText('Run context')).not.toBeVisible()
    await expect(page.getByText('Averix-AI').first()).toBeVisible()
    await expect(page.getByText('4255cdc').first()).toBeVisible()
  })

  test('empty states shown when no repository is selected on runs, evidence, and tool-traces pages', async ({ page }) => {
    await setupMockWorkspace(page)
    // No pre-seeded selection, 2 repos available -> no auto-selection

    await page.goto('/workspace/runs')
    await expect(page.getByText('Select a repository to view verification runs.').first()).toBeVisible()

    await page.goto('/workspace/evidence')
    await expect(page.getByText('Select a repository to view evidence.').first()).toBeVisible()

    await page.goto('/workspace/tool-traces')
    await expect(page.getByText('Select a repository to view tool traces.').first()).toBeVisible()
  })

  test('HUMAN_WAIT run displays editable decision form with obligation why_needed and authority', async ({ page }) => {
    await setupMockWorkspace(page)

    const humanWaitRun = {
      ...runForA,
      id: 'run-human-wait',
      status: 'HUMAN_WAIT',
      has_open_human_question: true
    }

    await page.route(`**/v1/verification-runs/${humanWaitRun.id}`, route => route.fulfill({
      json: {
        run: humanWaitRun,
        repository: { id: projectA.id, name: 'Averix-AI', full_name: projectA.name, repository_source_type: 'github_app' },
        snapshot: { id: snapshotA.id, requested_ref: 'main', resolved_commit_sha: snapshotA.resolved_commit_sha, status: 'READY' },
        plan: { id: 'plan-1', version: 1, change_request: 'Add dangerous pathway' },
        obligation_counts: { HUMAN_REQUIRED: 1 },
        human_questions: [
          {
            id: 'q-open-1',
            obligation_id: 'ob-hw-1',
            question: 'Is security exception approved for ticket SEC-500?',
            why_needed: 'Compliance gate requires security team review.',
            authority_required: 'Security Lead',
            status: 'OPEN',
            answer: null
          }
        ],
        tool_runs: [],
        evidence_count: 0,
        tool_execution_count: 0,
        trace_attribution_status: 'EXACT'
      }
    }))

    await page.route(`**/v1/verification-runs/${humanWaitRun.id}/proof-obligations`, route => route.fulfill({
      json: [
        {
          id: 'ob-hw-1',
          statement: 'Security exception signed off',
          category: 'SAFETY',
          criticality: 'CRITICAL',
          status: 'HUMAN_REQUIRED',
          evidence_ids: [],
          counter_evidence_ids: []
        }
      ]
    }))

    await page.route(`**/v1/verification-runs/${humanWaitRun.id}/evidence`, route => route.fulfill({ json: [] }))

    await page.goto(`/workspace/runs/${humanWaitRun.id}`)

    await expect(page.getByText('HUMAN DECISION REQUIRED').first()).toBeVisible()
    await expect(page.getByText('Authorized Human Decision Required')).toBeVisible()
    await expect(page.getByText('Is security exception approved for ticket SEC-500?').first()).toBeVisible()
    await expect(page.getByText('Security Lead').first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Submit decision' }).first()).toBeVisible()
  })

  test('Evidence and Tool Traces pages scope data to selected repository', async ({ page }) => {
    await setupMockWorkspace(page)

    // Pre-seed localStorage with Payment-Service as active workspace context
    await page.addInitScript(() => {
      localStorage.setItem('planproof:workspace-context:12345', JSON.stringify({
        repositoryId: 'proj-service',
        repositoryFullName: 'NikhilRaikwar/Payment-Service',
        ref: 'main',
        snapshotId: 'snap-8899aabb',
        commitSha: '8899aabbccddeeff1234567890abcdef12345678',
        snapshotStatus: 'READY',
        dataScope: 'USER'
      }))
    })

    // Evidence Explorer displays scoped run and snippet
    await page.goto('/workspace/evidence')
    await expect(page.getByText('Payment-Service').first()).toBeVisible()
    await expect(page.getByText('Unique constraint check verified on token parameter.')).toBeVisible()
    await expect(page.getByText('assertIdempotency')).toBeVisible()

    // Tool Traces displays scoped tool run with query summary
    await page.goto('/workspace/tool-traces')
    await expect(page.getByText('Payment-Service').first()).toBeVisible()
    await expect(page.getByText('search_code_lexical')).toBeVisible()
    await expect(page.getByText('assertIdempotency')).toBeVisible()
  })
})
