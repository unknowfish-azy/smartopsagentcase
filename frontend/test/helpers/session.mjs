export async function mockSession(page) {
  await page.route('**/api/auth/session', async route => {
    const user = await page.evaluate(() => {
      const stored = JSON.parse(localStorage.getItem('smartops_preview_auth') || '{}')
      return { id: stored.id || 1, username: stored.username || 'browser-test', role: stored.role || 'operator' }
    })
    await route.fulfill({ json: { code: 200, data: { user, csrfToken: 'browser-test-csrf' } } })
  })
}
