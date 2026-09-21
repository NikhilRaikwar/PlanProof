import { expect, Page, test } from '@playwright/test'

const run = { id: 'run-actual', project_id: 'project-1', snapshot_id: 'snap-1234567', plan_version_id: 'plan-1', status: 'BLOCKED', created_at: '2026-09-21T00:00:00Z', updated_at: '2026-09-21T00:00:00Z', tool_call_count: 2, model_call_count: 1 }
const snapshot = { id: 'snap-1234567', project_id: 'project-1', repository_identity: 'fixture:partial-refunds-v1', source_type: 'seeded_fixture', requested_ref: 'main', resolved_commit_sha: 'aabbccddeeff', status: 'READY', files_indexed: 4, symbols_indexed: 12, ignored_files: 0, supported_languages: ['python', 'typescript'], created_at: '2026-09-21T00:00:00Z', updated_at: '2026-09-21T00:00:00Z' }

async function mockApi(page: Page) {
  await page.route('**/health/ready', route => route.fulfill({ status: 200 }))
  await page.route('**/v1/auth/session', route => route.fulfill({ json: { connected: true, account_login: 'test-user', installation_id: 12345 } }))
  await page.route('**/v1/workspace/projects', route => route.fulfill({ json: [{ id: 'project-1', name: 'Partial Refund Demo', owner_id: 'test-user', repository_source_type: 'seeded_fixture', fixture_id: 'partial-refunds-v1', created_at: '2026-09-21T00:00:00Z' }] }))
  await page.route('**/v1/projects', route => route.fulfill({ json: [{ id: 'project-1', name: 'Partial Refund Demo', owner_id: 'test-user', repository_source_type: 'seeded_fixture', fixture_id: 'partial-refunds-v1', created_at: '2026-09-21T00:00:00Z' }] }))
  await page.route('**/v1/github/repositories', route => route.fulfill({ json: [] }))
  await page.route('**/v1/projects/project-1/snapshots', route => route.fulfill({ json: [snapshot] }))
  await page.route('**/v1/verification-runs/run-actual/proof-obligations', route => route.fulfill({ json: [{ id: 'ob-disproved', statement: 'Multiple refunds fit current schema', category: 'SCHEMA', criticality: 'HIGH', status: 'DISPROVED', evidence_ids: [], counter_evidence_ids: ['ev-1'] }, { id: 'ob-human', statement: 'Mobile client impact is known', category: 'CROSS_SERVICE', criticality: 'HIGH', status: 'HUMAN_REQUIRED', evidence_ids: [], counter_evidence_ids: [] }] }))
  await page.route('**/v1/verification-runs/run-actual/evidence', route => route.fulfill({ json: [{ id: 'ev-1', snapshot_id: snapshot.id, source_tool_run_id: 'tool-1', evidence_type: 'source_range', path: 'db/models/refund.ts', start_line: 9, end_line: 9, content_hash: 'ab'.repeat(32), safe_fact_summary: 'Unique constraint found.', created_at: '2026-09-21T00:00:00Z' }] }))
  await page.route('**/v1/verification-runs/run-actual/tool-runs', route => route.fulfill({ json: [{ id: 'tool-1', tool_name: 'search_code_lexical', status: 'SUCCEEDED', input_hash: 'cd'.repeat(32), result_count: 1, duration_ms: 12, started_at: '2026-09-21T00:00:00Z' }] }))
  await page.route('**/v1/verification-runs/run-actual', route => route.fulfill({ json: { run, obligation_counts: { DISPROVED: 1, HUMAN_REQUIRED: 1 }, human_questions: [{ id: 'question-1', obligation_id: 'ob-human', question: 'Does mobile consume this contract?', why_needed: 'Repository code cannot decide.', authority_required: 'Product owner', status: 'OPEN' }], tool_runs: [], evidence_count: 1 } }))
  await page.route('**/v1/verification-runs', route => route.fulfill({ json: [run] }))
}

test('repositories use empty and seeded API states without fixture fallback', async ({ page }) => {
  await page.route('**/v1/auth/session', route => route.fulfill({ json: { connected: true, account_login: 'test-user', installation_id: 12345 } }))
  await page.route('**/v1/projects', route => route.fulfill({ json: [] }))
  await page.route('**/v1/workspace/projects', route => route.fulfill({ json: [] }))
  await page.route('**/v1/github/repositories', route => route.fulfill({ json: [] }))
  await page.goto('/workspace/repositories')
  await expect(page.getByText('No repositories connected')).toBeVisible()
  await page.unroute('**/v1/projects')
  await page.unroute('**/v1/workspace/projects')
  await mockApi(page)
  await page.reload()
  await expect(page.getByText('Demo fixture')).toBeVisible()
  await expect(page.getByText('READY', { exact: true }).first()).toBeVisible()
})

test('runs, gate report, evidence, and trace are rendered from server records', async ({ page }) => {
  await mockApi(page)
  await page.goto('/workspace/runs')
  await expect(page.getByText('BLOCKED')).toBeVisible()
  await page.goto('/workspace/runs/run-actual')
  await expect(page.getByText('Gate: BLOCKED')).toBeVisible()
  await expect(page.getByText('Multiple refunds fit current schema')).toBeVisible()
  await page.goto('/workspace/evidence')
  await page.selectOption('select', 'run-actual')
  await expect(page.getByText('Unique constraint found.')).toBeVisible()
  await page.goto('/workspace/tool-traces')
  await page.selectOption('select', 'run-actual')
  await expect(page.getByText('search_code_lexical')).toBeVisible()
})

test('API failure is shown rather than substituted with mock product data', async ({ page }) => {
  await page.route('**/v1/auth/session', route => route.fulfill({ json: { connected: true, account_login: 'test-user', installation_id: 12345 } }))
  await page.route('**/v1/verification-runs', route => route.fulfill({ status: 503, json: { detail: 'unavailable' } }))
  await page.goto('/workspace/runs')
  await expect(page.getByText('unavailable')).toBeVisible()
  await expect(page.getByText('Partial Refunds / PlanGate')).not.toBeVisible()
})

test('internal quality remains an honest empty internal state', async ({ page }) => {
  await page.route('**/v1/evaluations/latest', route => route.fulfill({ status: 404, json: { detail: 'no evaluation runs recorded' } }))
  await page.goto('/internal/quality')
  await expect(page.getByText('No evaluation runs recorded yet.')).toBeVisible()
  await expect(page.getByText('248 runs')).not.toBeVisible()
})

test('workspace dashboard renders real data and session account', async ({ page }) => {
  await mockApi(page)
  await page.goto('/workspace')
  await expect(page.getByText('Verification Dashboard')).toBeVisible()
  await expect(page.getByRole('main').getByText('@test-user')).toBeVisible()
  await expect(page.getByText('Partial Refund Demo').first()).toBeVisible()
})

test('landing page shows Connect GitHub when disconnected and Open workspace when connected', async ({ page }) => {
  await page.route('**/v1/auth/session', route => route.fulfill({ status: 401, json: { detail: 'unauthorized' } }))
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Connect GitHub' }).first()).toBeVisible()

  await page.route('**/v1/auth/session', route => route.fulfill({ json: { connected: true, account_login: 'test-user', installation_id: 12345 } }))
  await page.reload()
  await expect(page.getByRole('link', { name: 'Open workspace' }).first()).toBeVisible()
})
