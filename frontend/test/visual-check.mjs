import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const baseUrl = process.env.SMARTOPS_VISUAL_BASE_URL || 'http://127.0.0.1:5173'
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const viewports = [375, 768, 1024, 1440, 1920]
const browser = await chromium.launch({ executablePath: edgePath, headless: true })
await mkdir('test-artifacts', { recursive: true })

try {
  for (const width of viewports) {
    const page = await browser.newPage({ viewport: { width, height: 900 } })
    await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' })
    assert.equal(await page.locator('.login-shell').count(), 1)
    const loginTitle = page.locator('.login-copy h1')
    assert.equal(await loginTitle.innerText(), '智驭系统\n维系上下文')
    assert.notEqual(await loginTitle.evaluate((element) => getComputedStyle(element).fontFamily), '')
    assert.ok(await page.locator('canvas').count() >= 1)
    await page.screenshot({ path: `test-artifacts/login-${width}.png`, fullPage: true })
    await page.route('**/api/auth/session', (route) => route.fulfill({ json: {
      code: 200,
      data: { user: { id: 1, username: 'visual-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'visual-csrf' }
    } }))
    await page.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'visual-test' })))
    await page.goto(baseUrl, { waitUntil: 'networkidle' })
    assert.equal(await page.locator('.home').count(), 1)
    assert.ok(await page.locator('canvas').count() >= 1)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
    await page.screenshot({ path: `test-artifacts/home-${width}.png`, fullPage: true })
    await page.close()
  }
  const reduced = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await reduced.emulateMedia({ reducedMotion: 'reduce' })
  await reduced.route('**/api/auth/session', (route) => route.fulfill({ json: {
    code: 200,
    data: { user: { id: 1, username: 'visual-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'visual-csrf' }
  } }))
  await reduced.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'visual-test' })))
  await reduced.goto(baseUrl, { waitUntil: 'networkidle' })
  assert.equal(await reduced.locator('.home').count(), 1)
  assert.ok(await reduced.locator('canvas').count() >= 1)
  await reduced.screenshot({ path: 'test-artifacts/home-reduced-motion.png', fullPage: true })
  await reduced.close()
} finally {
  await browser.close()
}
