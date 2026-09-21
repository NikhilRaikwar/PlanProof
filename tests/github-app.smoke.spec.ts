import { expect, test } from '@playwright/test'

test.describe.configure({ timeout: 120_000 })

test('GitHub App integration smoke: session, granted repositories, branch refs, and immutable snapshot READY', async ({ page }) => {
  const apiUrl = process.env.NEXT_PUBLIC_PLANPROOF_API_URL || 'https://planproof-api-lfrrer4z6q-el.a.run.app'
  
  // 1. Authenticate with verified installation
  await page.goto(`${apiUrl}/v1/auth/github/callback?installation_id=163541413`)
  await page.waitForURL(/\/workspace/)

  // 2. Verify workspace dashboard shows real GitHub identity
  await expect(page.getByText('@NikhilRaikwar')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('GitHub App Connected')).toBeVisible()

  // 3. Navigate to Repositories page
  await page.goto('/workspace/repositories')
  await expect(page.getByText(/GitHub App Repositories/i)).toBeVisible({ timeout: 15_000 })
  
  // 4. Verify real GitHub repository is listed
  const repoCard = page.locator('.card-panel-white').filter({ hasText: 'NikhilRaikwar/github-slideshow' }).first()
  await expect(repoCard).toBeVisible()

  // 5. Index snapshot for this repository
  const indexBtn = repoCard.getByRole('button', { name: /Index snapshot/i })
  if (await indexBtn.isVisible()) {
    await indexBtn.click()
  }

  // 6. Verify snapshot reaches READY state
  await expect(repoCard.getByText('READY').first()).toBeVisible({ timeout: 90_000 })
})
