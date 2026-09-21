import { expect, test } from '@playwright/test'

test.describe.configure({ timeout: 120_000 })

test('seeded fixture flows through the browser, Redis worker, human answer, and persisted blocked gate', async ({ page }) => {
  const tag = process.env.PLANPROOF_E2E_TAG || `local-${Date.now()}`
  const projectName = `e2e-seeded-${tag}`
  await page.goto('/workspace/repositories')
  await page.getByRole('button', { name: 'Add public repository' }).click()
  await page.locator('select').selectOption('seeded_fixture')
  await page.getByLabel('Display name (optional)').fill(projectName)
  await page.getByRole('button', { name: 'Create and index snapshot' }).click()
  // A post creates the project before asynchronous indexing begins. Reload the
  // actual browser route so the test observes persisted API state rather than
  // assuming one client-side refresh completed in the same render tick.
  await page.reload()
  await expect(page.getByText(projectName)).toBeVisible()
  const projectCard = page.locator('.card-panel-white').filter({ hasText: projectName })
  await expect(projectCard.getByText('READY')).toBeVisible({ timeout: 90_000 })

  await page.goto('/workspace/new-verification')
  const snapshotSelect = page.locator('select').first()
  const snapshotOption = snapshotSelect.locator('option', { hasText: projectName })
  await expect(snapshotOption).toHaveCount(1)
  const snapshotId = await snapshotOption.getAttribute('value')
  if (!snapshotId) throw new Error('The browser-created READY snapshot has no identifier.')
  await snapshotSelect.selectOption(snapshotId)
  await page.getByPlaceholder('Describe the engineering change...').fill('Add safe partial refunds while preserving idempotency and reviewing mobile contract impact.')
  await page.getByPlaceholder('Paste an engineering plan…').fill('Provider accepts a refund amount. Multiple refunds fit current schema. A product owner must explicitly approve whether any mobile client contract impact is acceptable.')
  await page.getByRole('button', { name: 'Verify this plan' }).click()
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
  // a fixture assertion.  Verify the rendered server record has a real
  // snapshot-relative path and source range without coupling to one filename.
  await expect(page.locator('strong').filter({ hasText: /.+:\d+-\d+/ }).first()).toBeVisible()
  await page.goto('/workspace/tool-traces')
  await page.locator('select').selectOption(runId)
  await expect(page.getByText('search_code_lexical')).toBeVisible()
})
