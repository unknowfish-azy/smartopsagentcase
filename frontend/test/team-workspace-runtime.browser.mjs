import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname), 'runtime check must stay on loopback')
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const context = await browser.newContext({ reducedMotion: 'reduce', serviceWorkers: 'block' })
  const writes = [], errors = []
  await context.route('**/api/**', route => {
    if (route.request().method() === 'GET') return route.continue()
    writes.push(route.request().method() + ' ' + new URL(route.request().url()).pathname)
    return route.abort()
  })
  for (const path of ['/api/teams', '/api/teams/invitations', '/api/admin/teams']) {
    const response = await context.request.get(`${base}${path}`)
    assert.equal(response.status(), 401, `${path} must reject anonymous access`)
  }
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  for (const path of ['/teams', '/teams/1', '/admin/teams']) {
    await page.goto(`${base}${path}`, { waitUntil: 'networkidle' })
    assert.equal(new URL(page.url()).pathname, '/login')
    await page.getByText('本地开发未启用人机验证，不代表公网已受保护。', { exact: true }).waitFor()
  }
  assert.deepEqual(writes, [])
  assert.deepEqual(errors, [])
  console.log('PASS live local team endpoints require authentication; all three routes redirect anonymous users; GET-only, no team/credential writes')
} finally { await browser.close() }
