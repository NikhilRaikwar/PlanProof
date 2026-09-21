import { expect, test } from '@playwright/test'

test.describe.configure({ timeout: 120_000 })

test('seeded fixture flows through the browser, Redis worker, human answer, and persisted blocked gate', async ({ page }) => {
  const tag = process.env.PLANPROOF_E2E_TAG || `local-${Date.now()}`
  const projectName = `e2e-seeded-${tag}`
  const apiUrl = process.env.NEXT_PUBLIC_PLANPROOF_API_URL || 'https://planproof-api-lfrrer4z6q-el.a.run.app'
  await page.goto(`${apiUrl}/v1/auth/github/callback?installation_id=163541413`)
  await page.waitForURL(/\/workspace/)
  await page.goto('/workspace/repositories')
  const demoBtn = page.getByTestId('index-demo-fixture').or(page.getByRole('button', { name: /Index demo fixture|Try Demo Fixture/i }))
  await demoBtn.click()
  await expect(page.getByText('Partial Refund Demo').first()).toBeVisible({ timeout: 15_000 })
  const projectCard = page.locator('.card-panel-white').filter({ hasText: 'Partial Refund Demo' }).first()
  await expect(projectCard.getByText('READY').first()).toBeVisible({ timeout: 90_000 })

  await page.goto('/workspace/new-verification')
  const snapshotSelect = page.locator('select').first()
  const snapshotOption = snapshotSelect.locator('option', { hasText: 'Partial Refund Demo' }).first()
  await expect(snapshotOption).toBeAttached()
  const snapshotId = await snapshotOption.getAttribute('value')
  if (!snapshotId) throw new Error('The browser-created READY snapshot has no identifier.')
  await snapshotSelect.selectOption(snapshotId)
  await page.locator('#change-request').or(page.getByLabel(/What are you planning to change/i)).fill('Add safe partial refunds while preserving idempotency and reviewing mobile contract impact.')
  await page.locator('#candidate-plan').or(page.getByLabel(/Candidate engineering plan/i)).fill('Provider accepts a refund amount. Multiple refunds fit current schema. A product owner must explicitly approve whether any mobile client contract impact is acceptable.')
  await page.getByRole('button', { name: /Verify this plan/i }).click()
  await page.waitForURL(/\/workspace\/runs\//)
  const runId = page.url().split('/').at(-1)
  if (!runId) throw new Error('Verification run route has no identifier.')
  await expect(page.getByText(/Gate:/)).toBeVisible()
  await expect(page.getByText('Human decision required')).toBeVisible({ timeout: 90_000 })
  await page.getByPlaceholder('Record the authorized decision…').fill('Product owner confirms the mobile contract impact.')
  await page.getByRole('button', { name: 'Submit decision' }).click()
  await expect(page.getByText('Gate: BLOCKED')).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText('DISPROVED', { exact: true }).first()).toBeVisible()
  // Evidence is discovered from the current seeded snapshot, never injected as
  // a fixture assertion. Verify the rendered server record has real server-issued evidence.
  await expect(page.getByRole('heading', { name: 'Evidence' })).toBeVisible()
  await expect(page.getByText(/Tool [0-9a-f]+/i).first()).toBeVisible()
  await page.goto('/workspace/tool-traces')
  await page.locator('select').selectOption(runId)
  await expect(page.getByText('search_code_lexical').first()).toBeVisible()
})
