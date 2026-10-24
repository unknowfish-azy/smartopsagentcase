import { chromium } from 'playwright'
import assert from 'node:assert/strict'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  await page.route('**/api/**', route => route.fulfill({ json: { code: 200, data: route.request().url().includes('/auth/session') ? { user: { id: 1, username: 'visual-review', role: 'operator', portal: 'user' }, csrfToken: 'x' } : [] } }))
  await page.goto('http://127.0.0.1:5190/', { waitUntil: 'networkidle' })
  await page.screenshot({ path: 'test-artifacts/ui-visual-home.png', fullPage: true }); console.log('URL',page.url(), 'HTML', (await page.locator('body').innerText()).slice(0,300))
  assert.equal((await page.locator('.home-heading__signal').textContent()).trim(), 'SYSTEM READY')
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  console.log('Home visual smoke passed.')
} finally { await browser.close() }


