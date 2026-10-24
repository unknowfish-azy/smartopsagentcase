import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname), 'runtime smoke test is local-only')
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const artifacts = new URL('../test-artifacts/human-verification-runtime/', import.meta.url)
await mkdir(artifacts, { recursive: true })

try {
  const context = await browser.newContext({ reducedMotion: 'reduce', serviceWorkers: 'block' })
  const errors = [], writes = [], responses = []
  await context.route('**/api/**', route => {
    if (route.request().method() === 'GET') return route.continue()
    writes.push(route.request().method() + ' ' + new URL(route.request().url()).pathname)
    return route.abort()
  })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  page.on('response', response => {
    if (new URL(response.url()).pathname.startsWith('/api/')) responses.push({ path: new URL(response.url()).pathname, status: response.status() })
  })
  for (const action of ['login', 'admin_login', 'register']) {
    const response = await context.request.get(`${base}/api/auth/human-verification`, { params: { action } })
    assert.equal(response.status(), 200, `${action}: running backend must expose the new public policy endpoint`)
    const { data } = await response.json()
    assert.equal(data.action, action)
    assert.equal(typeof data.enabled, 'boolean')
    assert.equal(typeof data.available, 'boolean')
    assert.equal('secretKey' in data, false)
    assert.equal(response.headers()['cache-control'], 'no-store')
    assert.equal(data.enabled, false, 'this smoke test expects explicit local development mode, not a production bypass')
  }
  for (const portal of ['user', 'admin']) {
    await page.goto(`${base}/login?portal=${portal}`, { waitUntil: 'networkidle' })
    await page.getByText('本地开发未启用人机验证，不代表公网已受保护。', { exact: true }).waitFor()
    assert.equal(await page.locator('.login-submit').isEnabled(), true)
    if (portal === 'user') {
      const registration = page.getByRole('button', { name: '注册普通账号', exact: true })
      if (await registration.isEnabled()) {
        await registration.click()
        await page.getByRole('heading', { name: '注册普通账号', exact: true }).waitFor()
        await page.waitForFunction(() => !document.querySelector('.login-submit').disabled)
        await page.getByRole('button', { name: '返回登录', exact: true }).click()
        await page.waitForFunction(() => !document.querySelector('.login-submit').disabled)
      }
    }
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('选择主题模式').selectOption(theme)
      await page.waitForFunction(() => !document.querySelector('.login-submit').disabled)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
      await page.screenshot({ path: fileURLToPath(new URL(`${portal}-${theme}.png`, artifacts)), fullPage: true })
    }
  }
  assert.deepEqual(writes, [], 'no credentials, registrations or other write operations are submitted')
  assert.deepEqual(errors, [])
  assert.deepEqual(responses.filter(response => response.status >= 400), [])
  console.log('PASS running local backend: three public verification policies, both login portals, available registration UI, theme switching; GET-only, no credentials submitted')
} finally {
  await browser.close()
}
